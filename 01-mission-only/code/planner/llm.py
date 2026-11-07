"""LLM API 클라이언트(OpenAI / Gemini)와 1차 추천(JSON) 단계.

둘 다 REST API에 POST 요청을 보낸다. (보낼 데이터 = 프롬프트가 요청 본문(body)에 실림)
지도 검색은 '조회'라서 GET + 쿼리스트링을 쓰는 것과 비교해 보자.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Protocol

from .errors import PARSE_ERROR, VALIDATION_ERROR, APIError, ErrorLog, request_json

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str: ...


class OpenAIClient:
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.name = f"openai:{model}"
        self._api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = request_json(
            "POST",
            self.URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json_body=body,
            timeout=self.timeout,
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise APIError(PARSE_ERROR, "OpenAI 응답에 choices[0].message.content 가 없습니다")


class GeminiClient:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.name = f"gemini:{model}"
        self._api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
        }
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        data = request_json(
            "POST",
            self.URL.format(model=self.model),
            # 키를 URL(?key=...)이 아닌 헤더로 보내야 로그/오류 메시지에 URL이 찍혀도 안전하다.
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            json_body=body,
            timeout=self.timeout,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            reason = ""
            if isinstance(data, dict):
                reason = str(data.get("promptFeedback") or "")[:120]
            raise APIError(PARSE_ERROR, f"Gemini 응답에 candidates 텍스트가 없습니다 {reason}".strip())


# ---------------------------------------------------------------------------
# 1차 추천: 날짜 -> 추천 지역/날씨/행사/이유 (JSON)
# ---------------------------------------------------------------------------

RECOMMEND_SYSTEM = (
    "당신은 대한민국 국내 여행 전문가입니다. "
    "항상 유효한 JSON 객체 하나만 출력합니다. 마크다운, 코드블록, 설명 문장을 붙이지 않습니다."
)


def describe_date(d: date) -> str:
    return f"{d.isoformat()} ({WEEKDAYS[d.weekday()]}요일, {d.month}월 {_period(d.day)})"


def _period(day: int) -> str:
    return "초순" if day <= 10 else ("중순" if day <= 20 else "하순")


def build_recommend_prompt(d: date, num_cities: int) -> str:
    multi = ""
    if num_cities > 1:
        multi = f"""
  "recommended_cities": [   // 정확히 {num_cities}개. 첫 번째 항목은 recommended_city와 같은 도시
    {{"city": string, "weather": string, "events": [string], "reason": string}}
  ]"""
    return f"""여행 날짜: {describe_date(d)}

이 시기에 국내에서 여행하기 좋은 지역을 추천해 주세요.
아래 스키마를 정확히 지킨 JSON 객체 하나만 출력하세요.

{{
  "recommended_city": string,   // 도시/지역 이름 하나 (예: "제주", "강릉", "경주"). 지도 검색어로 쓰이므로 짧게
  "weather": string,            // 해당 시기의 일반적인 날씨 요약 1~2문장
  "events": [string],           // 이 시기의 행사/축제 후보 1~3개
  "reason": string{"," if multi else ""}             // 추천 근거 2~4문장{multi}
}}

규칙:
- 키 이름과 타입을 바꾸지 마세요.
- 행사 날짜가 해마다 달라질 수 있으면 "(일정 변동 가능)"을 붙이세요.
- JSON 외의 텍스트는 절대 출력하지 마세요."""


def build_retry_prompt(d: date, num_cities: int, problem: str) -> str:
    keys = '"recommended_city"(string), "weather"(string), "events"(array of string, 1~3개), "reason"(string)'
    if num_cities > 1:
        keys += f', "recommended_cities"(array of {{city, weather, events, reason}} 객체, {num_cities}개)'
    return f"""이전 응답을 JSON으로 해석할 수 없었습니다. (문제: {problem})

여행 날짜: {describe_date(d)}
필수 키만 포함한 JSON 객체 하나만 다시 출력하세요: {keys}
첫 글자는 반드시 '{{', 마지막 글자는 반드시 '}}' 여야 합니다. 다른 텍스트는 금지합니다."""


def extract_json(text: str) -> Any:
    """LLM 출력에서 JSON 객체를 꺼낸다. 코드블록/앞뒤 설명이 섞여도 최대한 복구한다."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])  # 실패하면 JSONDecodeError가 그대로 올라감
    raise json.JSONDecodeError("JSON 객체를 찾을 수 없음", cleaned, 0)


def _city_entry(obj: Any, where: str) -> dict[str, Any]:
    """{recommended_city|city, weather, events, reason} 검증 + 정규화."""
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: 객체가 아닙니다")
    city = obj.get("recommended_city", obj.get("city"))
    problems = []
    if not isinstance(city, str) or not city.strip():
        problems.append("recommended_city(string) 누락")
    if not isinstance(obj.get("weather"), str) or not obj["weather"].strip():
        problems.append("weather(string) 누락")
    events = obj.get("events")
    if isinstance(events, str):
        events = [events]
    if not isinstance(events, list) or not all(isinstance(e, str) for e in events):
        problems.append("events(array of string) 형식 오류")
    if not isinstance(obj.get("reason"), str) or not obj["reason"].strip():
        problems.append("reason(string) 누락")
    if problems:
        raise ValueError(f"{where}: " + ", ".join(problems))
    events = [e.strip() for e in events if e.strip()][:3]
    if not events:
        raise ValueError(f"{where}: events가 비어 있습니다")
    return {
        "city": city.strip(),
        "weather": obj["weather"].strip(),
        "events": events,
        "reason": obj["reason"].strip(),
    }


def validate_recommendation(data: Any, num_cities: int, errors: ErrorLog) -> dict[str, Any]:
    """필수 스키마를 검증하고 정규화된 추천 결과를 돌려준다.

    반환 형식:
      {"recommended_city", "weather", "events", "reason", "recommended_cities": [{city, ...}]}
    필수 키가 깨지면 ValueError(재시도 대상). 보너스(복수 도시)만 깨지면 오류만 기록하고 1개 도시로 진행.
    """
    primary = _city_entry(data, "1차 추천")
    cities = [primary]

    if num_cities > 1:
        extra = data.get("recommended_cities") if isinstance(data, dict) else None
        if not isinstance(extra, list):
            errors.add("recommend", VALIDATION_ERROR, "recommended_cities 누락 - 1개 도시로 진행")
        else:
            seen = {primary["city"]}
            for i, item in enumerate(extra):
                try:
                    entry = _city_entry(item, f"recommended_cities[{i}]")
                except ValueError as exc:
                    errors.add("recommend", VALIDATION_ERROR, f"{exc} - 해당 항목 제외")
                    continue
                if entry["city"] not in seen:
                    seen.add(entry["city"])
                    cities.append(entry)
            cities = cities[:num_cities]

    return {
        "recommended_city": primary["city"],
        "weather": primary["weather"],
        "events": primary["events"],
        "reason": primary["reason"],
        "recommended_cities": cities,
    }


class RecommendationError(Exception):
    pass


def recommend(client: LLMClient, d: date, num_cities: int, errors: ErrorLog) -> dict[str, Any]:
    """1차 추천 생성. JSON 파싱/검증 실패 시 '필수 키만 다시' 프롬프트로 딱 1회만 재시도."""
    prompt = build_recommend_prompt(d, num_cities)
    for attempt in (1, 2):  # 최대 2회 = 최초 1회 + 재시도 1회 (무한 재시도 금지)
        try:
            raw = client.complete(RECOMMEND_SYSTEM, prompt, json_mode=True)
        except APIError as exc:
            errors.add("recommend", exc.type, exc.message)
            raise RecommendationError(f"LLM 호출 실패 ({exc.type}): {exc.message}") from exc

        try:
            return validate_recommendation(extract_json(raw), num_cities, errors)
        except (json.JSONDecodeError, ValueError) as exc:
            problem = str(exc)[:150]
            kind = PARSE_ERROR if isinstance(exc, json.JSONDecodeError) else VALIDATION_ERROR
            errors.add("recommend", kind, f"시도 {attempt}: {problem}")
            if attempt == 1:
                print("    - JSON 파싱 실패, 필수 키만 다시 요청합니다 (재시도 1회)")
                prompt = build_retry_prompt(d, num_cities, problem)

    raise RecommendationError("LLM 응답을 JSON으로 해석하지 못했습니다 (재시도 1회 후 실패)")
