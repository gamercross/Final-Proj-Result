#!/usr/bin/env python3
"""국내 여행 추천 프로그램.

흐름: 날짜 입력 → (LLM) 1차 추천 JSON → (Kakao Local) 맛집 검색 → (LLM) 최종 리포트
결과: results/{date}_data.json, results/{date}_travel_plan.md, results/{date}_travel_plan.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

try:  # python-dotenv 는 선택 사항. 있으면 .env 를 읽는다.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_KAKAO_BASE_URL = "https://dapi.kakao.com"
RESTAURANT_COUNT = 5
RESULTS_DIR = Path("results")
SECRET_ENV_NAMES = ("OPENAI_API_KEY", "KAKAO_REST_API_KEY")

# (연결 타임아웃, 응답 대기 타임아웃) 초
LLM_TIMEOUT = (10, 90)
PLACE_TIMEOUT = (5, 15)

SECTION_TITLES = [
    "추천 지역",
    "추천 이유",
    "날씨 요약",
    "행사/축제",
    "맛집 추천",
    "1일 일정 제안",
    "오류 요약(errors)",
]


# ---------------------------------------------------------------------------
# 키 가리기 (화면 출력 / 결과 파일 어디에도 키가 남지 않도록)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-*.]{4,}"),  # OpenAI 형식 키 (부분 노출 포함)
    re.compile(r"(KakaoAK\s+)\S+"),  # 인증 머리글
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
]


def redact(text: Any) -> Any:
    """문자열 안의 키 값을 '***' 로 바꾼다. 문자열이 아니면 그대로 돌려준다."""
    if not isinstance(text, str):
        return text
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            text = text.replace(value, "***")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "***", text)
        else:
            text = pattern.sub("***", text)
    return text


def redact_obj(obj: Any) -> Any:
    """dict/list 안의 모든 문자열에 redact 를 적용한다."""
    if isinstance(obj, dict):
        return {redact_obj(k): redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return redact(obj)


def log(message: str = "") -> None:
    print(redact(message), flush=True)


def log_err(message: str) -> None:
    print(redact(message), file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# 오류 표현
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """외부 API 호출 실패. type 은 AUTH_ERROR / QUOTA_ERROR / NETWORK_ERROR / HTTP_ERROR / PARSE_ERROR."""

    def __init__(self, error_type: str, message: str, status: int | None = None):
        super().__init__(message)
        self.type = error_type
        self.message = redact(message)
        self.status = status


def add_error(errors: list[dict], step: str, error_type: str, message: str) -> None:
    errors.append({"step": step, "type": error_type, "message": redact(str(message))[:500]})


def _short_body(resp: requests.Response) -> str:
    """오류 응답 본문에서 짧은 설명만 뽑는다."""
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip()[:200]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:200]
        for key in ("message", "msg", "errorType"):
            if data.get(key):
                return str(data[key])[:200]
    return json.dumps(data, ensure_ascii=False)[:200]


def _http_error(resp: requests.Response) -> ApiError:
    status = resp.status_code
    detail = _short_body(resp)
    message = f"HTTP {status}" + (f": {detail}" if detail else "")
    if status in (401, 403):
        return ApiError("AUTH_ERROR", message, status)
    if status == 429:
        return ApiError("QUOTA_ERROR", message, status)
    return ApiError("HTTP_ERROR", message, status)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


def load_env_files() -> None:
    """.env 파일을 읽는다(이미 설정된 환경변수가 우선)."""
    if load_dotenv is None:
        return
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def load_config() -> dict:
    """필수 키를 확인한다. 없으면 외부 호출 전에 종료 코드 1로 끝낸다."""
    missing = [name for name in SECRET_ENV_NAMES if not os.environ.get(name, "").strip()]
    if missing:
        log_err("오류: 필요한 API 키 환경변수가 설정되지 않았습니다: " + ", ".join(missing))
        log_err("")
        log_err("설정 방법 (택1):")
        log_err("  1) 프로젝트 폴더에 .env 파일을 만들고 아래처럼 적습니다 (.env.example 참고).")
        for name in missing:
            log_err(f"       {name}=발급받은_키")
        log_err("  2) 현재 터미널 세션에 환경변수로 설정합니다.")
        for name in missing:
            log_err(f'       macOS/Linux : export {name}="발급받은_키"')
            log_err(f'       PowerShell  : $env:{name}="발급받은_키"')
        log_err("")
        log_err("자세한 내용은 README.md 의 'API 키 설정' 절을 참고하세요.")
        sys.exit(1)

    return {
        "openai_key": os.environ["OPENAI_API_KEY"].strip(),
        "openai_base": (os.environ.get("OPENAI_BASE_URL", "").strip() or DEFAULT_OPENAI_BASE_URL).rstrip("/"),
        "openai_model": os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL,
        "kakao_key": os.environ["KAKAO_REST_API_KEY"].strip(),
        "kakao_base": (os.environ.get("KAKAO_BASE_URL", "").strip() or DEFAULT_KAKAO_BASE_URL).rstrip("/"),
    }


# ---------------------------------------------------------------------------
# LLM (OpenAI Chat Completions)
# ---------------------------------------------------------------------------


def call_llm(cfg: dict, messages: list[dict], json_mode: bool = True) -> str:
    """POST {base}/chat/completions 를 호출하고 응답 텍스트를 돌려준다."""
    url = f"{cfg['openai_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['openai_key']}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {"model": cfg["openai_model"], "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=LLM_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError("NETWORK_ERROR", f"네트워크 오류 ({type(exc).__name__})") from None

    if resp.status_code != 200:
        raise _http_error(resp)

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ApiError("PARSE_ERROR", "LLM 응답에서 choices[0].message.content 를 찾을 수 없습니다") from None
    if not isinstance(content, str) or not content.strip():
        raise ApiError("PARSE_ERROR", "LLM 응답 내용이 비어 있습니다")
    return content


def extract_json(text: str) -> dict:
    """LLM 텍스트에서 JSON 객체를 꺼낸다. ```json 코드 블록이나 앞뒤 설명도 허용."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("JSON 객체를 찾을 수 없습니다") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 파싱 실패: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ValueError("최상위가 JSON 객체가 아닙니다")
    return data


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate_recommendation(data: dict) -> dict:
    """1차 추천 스키마를 확인하고 정리된 dict 를 돌려준다. 맞지 않으면 ValueError."""
    problems = []
    for key in ("recommended_city", "weather", "reason"):
        if not _nonempty_str(data.get(key)):
            problems.append(f"'{key}'(비어 있지 않은 문자열)")
    events = data.get("events")
    if not isinstance(events, list) or not all(isinstance(e, str) for e in events):
        problems.append("'events'(문자열 배열)")
        events = []
    events = [e.strip() for e in events if e.strip()]
    if not problems and not events:
        problems.append("'events'(1~3개)")
    if problems:
        raise ValueError("필수 키 누락/형식 오류: " + ", ".join(problems))
    return {
        "recommended_city": data["recommended_city"].strip(),
        "weather": data["weather"].strip(),
        "events": events[:3],
        "reason": data["reason"].strip(),
    }


RECOMMEND_SYSTEM = (
    "당신은 대한민국 국내 여행 전문가입니다. 반드시 JSON 객체 하나만 출력하세요. "
    "설명 문장, 마크다운, 코드 블록은 출력하지 마세요."
)


def recommend_prompt(date: str) -> str:
    return f"""여행 날짜: {date}

이 날짜(계절/시기)에 여행하기 좋은 대한민국 국내 도시 1곳을 추천하세요.
아래 스키마의 JSON 객체 하나만 출력하세요.

{{
  "recommended_city": "도시 이름 (string, 예: \\"제주\\", \\"강릉\\", 장소 검색에 쓸 수 있게 짧게)",
  "weather": "해당 시기의 일반적인 날씨 요약 (string, 한 문장)",
  "events": ["행사/축제 후보 (string)", "1~3개"],
  "reason": "추천 근거 (string, 2~4문장)"
}}

규칙:
- 키 이름은 정확히 recommended_city, weather, events, reason 네 개만 사용합니다.
- events 는 문자열 1~3개로 된 배열입니다. 일정이 불확실하면 "(일정 변동 가능)"을 덧붙입니다.
- 모든 값은 한국어로 작성합니다."""


def recommend_retry_prompt(date: str, problem: str) -> str:
    return f"""직전 응답을 처리하지 못했습니다 ({problem}).
여행 날짜 {date} 기준으로, 필수 키만 담은 JSON 객체 하나만 다시 출력하세요. 다른 글자는 쓰지 마세요.

{{"recommended_city": "string", "weather": "string", "events": ["string (1~3개)"], "reason": "string (2~4문장)"}}"""


def get_recommendation(cfg: dict, date: str, errors: list[dict]) -> dict:
    """1차 추천. 실패하면 딱 한 번 다시 요청하고, 또 실패하면 종료 코드 1."""
    messages = [
        {"role": "system", "content": RECOMMEND_SYSTEM},
        {"role": "user", "content": recommend_prompt(date)},
    ]
    last_problem = ""
    for attempt in (1, 2):
        try:
            text = call_llm(cfg, messages)
            return validate_recommendation(extract_json(text))
        except ApiError as exc:
            last_problem = exc.message
            add_error(errors, "recommendation", exc.type, exc.message)
            log(f"  - 오류: LLM 호출 실패 ({exc.message})")
            if exc.type == "AUTH_ERROR":
                log("    OPENAI_API_KEY 값이 올바른지, 사용 권한이 있는지 확인하세요.")
                break  # 인증 오류는 다시 해도 같으므로 바로 종료
            if exc.type == "QUOTA_ERROR":
                log("    사용량 한도(쿼터)/결제 상태를 확인하세요.")
        except ValueError as exc:
            last_problem = str(exc)
            add_error(errors, "recommendation", "PARSE_ERROR", str(exc))
            log(f"  - 오류: 추천 JSON 을 읽지 못했습니다 ({exc})")
            # 다음 시도는 "필수 키만 다시 JSON으로" 요청
            messages = [
                {"role": "system", "content": RECOMMEND_SYSTEM},
                {"role": "user", "content": recommend_retry_prompt(date, str(exc))},
            ]
        if attempt == 1:
            log("  - 한 번만 다시 요청합니다...")

    log_err(f"오류: 1차 추천을 만들지 못해 종료합니다. ({last_problem})")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 지도 (Kakao Local 키워드 검색)
# ---------------------------------------------------------------------------


def _to_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # NaN 제외


def search_restaurants(cfg: dict, city: str, errors: list[dict]) -> list[dict]:
    """GET {base}/v2/local/search/keyword.json 으로 맛집을 찾는다. 실패해도 빈 목록을 돌려준다."""
    url = f"{cfg['kakao_base']}/v2/local/search/keyword.json"
    query = f"{city} 맛집"
    params = {"query": query, "size": RESTAURANT_COUNT}
    headers = {"Authorization": f"KakaoAK {cfg['kakao_key']}"}

    def fail(error_type: str, message: str, hint: str = "") -> list[dict]:
        add_error(errors, "place_search", error_type, message)
        log(f"  - 오류: {message}" + (f". {hint}" if hint else ""))
        log("  - 맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=PLACE_TIMEOUT)
    except requests.RequestException as exc:
        return fail("NETWORK_ERROR", f"네트워크 오류 ({type(exc).__name__})")

    if resp.status_code in (401, 403):
        return fail(
            "AUTH_ERROR",
            f"인증 실패(HTTP {resp.status_code})",
            "KAKAO_REST_API_KEY 값과 앱의 카카오맵(Local) 사용 설정을 확인하세요",
        )
    if resp.status_code == 429:
        return fail("QUOTA_ERROR", "요청 한도 초과(HTTP 429)", "잠시 후 다시 실행하거나 쿼터를 확인하세요")
    if resp.status_code != 200:
        # 그 밖의 서버/요청 오류도 '통신 실패'로 묶어 기록한다.
        detail = _short_body(resp)
        return fail("NETWORK_ERROR", f"HTTP {resp.status_code}" + (f": {detail}" if detail else ""))

    try:
        documents = resp.json().get("documents")
        if not isinstance(documents, list):
            raise ValueError
    except (ValueError, AttributeError):
        return fail("NETWORK_ERROR", "장소 API 응답을 해석할 수 없습니다(JSON 형식 아님)")

    restaurants = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("place_name") or "").strip()
        x, y = _to_number(doc.get("x")), _to_number(doc.get("y"))
        if not name or x is None or y is None:
            continue
        restaurants.append(
            {
                "name": name,
                "address": str(doc.get("road_address_name") or doc.get("address_name") or "").strip(),
                "category": str(doc.get("category_name") or "").strip(),
                "url": str(doc.get("place_url") or "").strip(),
                "x": x,
                "y": y,
            }
        )
        if len(restaurants) >= RESTAURANT_COUNT:
            break

    if not restaurants:
        add_error(errors, "place_search", "EMPTY_RESULT", f"0 results for query={query}")
        log("  - 검색 결과 0건 (다시 찾지 않고 다음 단계로 진행)")
        return []

    log(f"  - 맛집 {len(restaurants)}곳 검색 완료")
    return restaurants


# ---------------------------------------------------------------------------
# 최종 리포트 (LLM 이 내용을 쓰고, 절 제목은 프로그램이 보장)
# ---------------------------------------------------------------------------

REPORT_SYSTEM = (
    "당신은 국내 여행 리포트를 쓰는 작가입니다. 반드시 JSON 객체 하나만 출력하세요. "
    "값에는 마크다운 제목(#)이나 HTML 태그를 쓰지 말고 평범한 한국어 문장만 쓰세요."
)


def report_prompt(date: str, rec: dict, restaurants: list[dict]) -> str:
    payload = {
        "date": date,
        "recommendation": rec,
        "restaurants": [
            {"name": r["name"], "category": r["category"], "address": r["address"]} for r in restaurants
        ],
    }
    restaurant_rule = (
        "- 일정에서 식당을 언급할 때는 restaurants 에 있는 이름만 사용합니다."
        if restaurants
        else "- restaurants 가 비어 있으므로 특정 식당 이름을 지어내지 말고 '현지 음식' 같은 일반 표현을 씁니다."
    )
    return f"""아래 데이터로 여행 리포트의 본문을 써 주세요.

{json.dumps(payload, ensure_ascii=False, indent=2)}

아래 스키마의 JSON 객체 하나만 출력하세요.
{{
  "region_summary": "추천 지역 소개 (1~2문장)",
  "reason_summary": "추천 이유 요약 (2~3문장)",
  "weather_summary": "날씨 요약과 옷차림/준비물 팁 (1~2문장)",
  "itinerary": {{
    "morning": "오전 일정 (1~2문장)",
    "afternoon": "오후 일정 (1~2문장)",
    "evening": "저녁 일정 (1~2문장)"
  }}
}}

규칙:
- 모든 값은 비어 있지 않은 문자열입니다.
{restaurant_rule}
- 행사/축제는 recommendation.events 에 있는 것만 언급합니다."""


def validate_report(data: dict) -> dict:
    problems = [k for k in ("region_summary", "reason_summary", "weather_summary") if not _nonempty_str(data.get(k))]
    itinerary = data.get("itinerary")
    if not isinstance(itinerary, dict):
        problems.append("itinerary")
        itinerary = {}
    problems += [f"itinerary.{k}" for k in ("morning", "afternoon", "evening") if not _nonempty_str(itinerary.get(k))]
    if problems:
        raise ValueError("필수 키 누락/형식 오류: " + ", ".join(problems))
    return {
        "region_summary": data["region_summary"].strip(),
        "reason_summary": data["reason_summary"].strip(),
        "weather_summary": data["weather_summary"].strip(),
        "itinerary": {k: itinerary[k].strip() for k in ("morning", "afternoon", "evening")},
    }


def fallback_report(rec: dict, restaurants: list[dict]) -> dict:
    """리포트 LLM 이 실패했을 때 가진 데이터만으로 본문을 만든다."""
    city = rec["recommended_city"]
    events = rec["events"]
    lunch = f"점심은 '{restaurants[0]['name']}'에서 현지 음식을 맛봅니다." if restaurants else "점심은 현지 음식을 맛봅니다."
    dinner = (
        f"저녁은 '{restaurants[1]['name'] if len(restaurants) > 1 else restaurants[0]['name']}'에서 식사하며 하루를 마무리합니다."
        if restaurants
        else "저녁은 현지 시장이나 먹거리 골목에서 식사하며 하루를 마무리합니다."
    )
    afternoon = f"오후에는 '{events[0]}'에 들러 지역 분위기를 즐깁니다." if events else "오후에는 주요 관광지를 둘러봅니다."
    return {
        "region_summary": f"{city}을(를) 추천합니다.",
        "reason_summary": rec["reason"],
        "weather_summary": rec["weather"],
        "itinerary": {
            "morning": f"{city}의 대표 명소를 산책하며 여행을 시작합니다. {lunch}",
            "afternoon": afternoon,
            "evening": dinner,
        },
    }


def write_report_content(cfg: dict, date: str, rec: dict, restaurants: list[dict], errors: list[dict]) -> dict:
    messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {"role": "user", "content": report_prompt(date, rec, restaurants)},
    ]
    for attempt in (1, 2):
        try:
            content = validate_report(extract_json(call_llm(cfg, messages)))
            log("  - 리포트 생성 완료")
            return content
        except ApiError as exc:
            add_error(errors, "report", exc.type, exc.message)
            log(f"  - 오류: 리포트 LLM 호출 실패 ({exc.message})")
            break  # 호출 자체가 실패하면 다시 하지 않고 대체 리포트로 진행
        except ValueError as exc:
            add_error(errors, "report", "PARSE_ERROR", str(exc))
            log(f"  - 오류: 리포트 JSON 을 읽지 못했습니다 ({exc})")
            if attempt == 1:
                log("  - 한 번만 다시 요청합니다...")
                messages = messages + [
                    {"role": "user", "content": f"직전 응답을 처리하지 못했습니다 ({exc}). 스키마의 필수 키만 담은 JSON 객체 하나만 다시 출력하세요."}
                ]
    log("  - 가진 데이터로 리포트를 만듭니다.")
    return fallback_report(rec, restaurants)


# ---------------------------------------------------------------------------
# 출력 (Markdown / HTML)
# ---------------------------------------------------------------------------


def md_text(text: str) -> str:
    """바깥 글을 Markdown 에 안전하게 넣는다: 제목(#) 줄 무력화, < > 이스케이프."""
    lines = [re.sub(r"^\s*#+\s*", "", line) for line in str(text).splitlines()]
    joined = " ".join(line.strip() for line in lines if line.strip())
    return joined.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def safe_url(url: str) -> str:
    return url if re.match(r"^https?://", url or "", re.IGNORECASE) else ""


def render_markdown(date: str, rec: dict, restaurants: list[dict], content: dict, errors: list[dict]) -> str:
    t = SECTION_TITLES
    out = [f"# {date} 국내 여행 추천 리포트", ""]

    out += [f"## {t[0]}", "", f"**{md_text(rec['recommended_city'])}**", "", md_text(content["region_summary"]), ""]
    out += [f"## {t[1]}", "", md_text(content["reason_summary"]), ""]
    out += [f"## {t[2]}", "", md_text(content["weather_summary"]), ""]

    out += [f"## {t[3]}", ""]
    out += [f"- {md_text(e)}" for e in rec["events"]] or ["- 데이터 없음"]
    out += ["", "> 행사 일정은 변동될 수 있으니 방문 전 공식 안내를 확인하세요.", ""]

    out += [f"## {t[4]}", ""]
    if restaurants:
        for i, r in enumerate(restaurants, 1):
            line = f"{i}. **{md_text(r['name'])}**"
            if r["category"]:
                line += f" ({md_text(r['category'])})"
            if r["address"]:
                line += f" — {md_text(r['address'])}"
            if safe_url(r["url"]):
                line += f" — [지도 보기]({r['url']})"
            out.append(line)
    else:
        reason = "장소 검색 결과 0건" if any(e["type"] == "EMPTY_RESULT" for e in errors) else "장소 검색 실패"
        out.append(f"- 데이터 없음 ({reason})")
    out.append("")

    it = content["itinerary"]
    out += [
        f"## {t[5]}",
        "",
        f"- **오전**: {md_text(it['morning'])}",
        f"- **오후**: {md_text(it['afternoon'])}",
        f"- **저녁**: {md_text(it['evening'])}",
        "",
    ]

    out += [f"## {t[6]}", ""]
    if errors:
        out += [f"- `{e['step']}` / `{e['type']}`: {md_text(e['message'])}" for e in errors]
    else:
        out.append("- 없음")
    out.append("")
    return "\n".join(out)


HTML_STYLE = """
body{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
max-width:760px;margin:40px auto;padding:0 20px;line-height:1.7;color:#222}
h1{border-bottom:3px solid #2b7a78;padding-bottom:8px}
h2{color:#2b7a78;margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:4px}
.city{font-size:1.4em;font-weight:bold}
.note{color:#777;font-size:.9em}
code{background:#f3f3f3;padding:1px 4px;border-radius:3px}
li{margin:4px 0}
"""


def render_html(date: str, rec: dict, restaurants: list[dict], content: dict, errors: list[dict]) -> str:
    e = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    t = SECTION_TITLES
    parts = [
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{e(date)} 국내 여행 추천 리포트</title>",
        f"<style>{HTML_STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{e(date)} 국내 여행 추천 리포트</h1>",
        f"<h2>{e(t[0])}</h2>",
        f'<p class="city">{e(rec["recommended_city"])}</p>',
        f"<p>{e(content['region_summary'])}</p>",
        f"<h2>{e(t[1])}</h2>",
        f"<p>{e(content['reason_summary'])}</p>",
        f"<h2>{e(t[2])}</h2>",
        f"<p>{e(content['weather_summary'])}</p>",
        f"<h2>{e(t[3])}</h2>",
        "<ul>",
    ]
    parts += [f"<li>{e(ev)}</li>" for ev in rec["events"]] or ["<li>데이터 없음</li>"]
    parts += ["</ul>", '<p class="note">행사 일정은 변동될 수 있으니 방문 전 공식 안내를 확인하세요.</p>']

    parts.append(f"<h2>{e(t[4])}</h2>")
    if restaurants:
        parts.append("<ol>")
        for r in restaurants:
            item = f"<strong>{e(r['name'])}</strong>"
            if r["category"]:
                item += f" ({e(r['category'])})"
            if r["address"]:
                item += f" — {e(r['address'])}"
            if safe_url(r["url"]):
                item += f' — <a href="{e(r["url"])}" rel="noopener noreferrer">지도 보기</a>'
            parts.append(f"<li>{item}</li>")
        parts.append("</ol>")
    else:
        reason = "장소 검색 결과 0건" if any(x["type"] == "EMPTY_RESULT" for x in errors) else "장소 검색 실패"
        parts.append(f"<ul><li>데이터 없음 ({e(reason)})</li></ul>")

    it = content["itinerary"]
    parts += [
        f"<h2>{e(t[5])}</h2>",
        "<ul>",
        f"<li><strong>오전</strong>: {e(it['morning'])}</li>",
        f"<li><strong>오후</strong>: {e(it['afternoon'])}</li>",
        f"<li><strong>저녁</strong>: {e(it['evening'])}</li>",
        "</ul>",
        f"<h2>{e(t[6])}</h2>",
        "<ul>",
    ]
    if errors:
        parts += [
            f"<li><code>{e(x['step'])}</code> / <code>{e(x['type'])}</code>: {e(x['message'])}</li>" for x in errors
        ]
    else:
        parts.append("<li>없음</li>")
    parts += ["</ul>", "</body>", "</html>", ""]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 저장 / CLI
# ---------------------------------------------------------------------------


def save_text(path: Path, text: str) -> None:
    path.write_text(redact(text), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 입력하면 LLM + 지도 API로 국내 여행 리포트를 만듭니다.",
    )
    parser.add_argument("-date", "--date", required=True, metavar="YYYY-MM-DD", help="여행 날짜 (예: 2026-03-15)")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="results/{date}_data.json 이 있으면 API 호출 없이 그 데이터로 리포트를 다시 만듭니다.",
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error(f"날짜 형식이 올바르지 않습니다: {args.date!r} (YYYY-MM-DD 형식으로 입력하세요)")
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error(f"존재하지 않는 날짜입니다: {args.date!r}")
    return args


def load_cache(path: Path) -> tuple[dict, list[dict], list[dict]] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = validate_recommendation(data["recommendation"])
        restaurants = data["restaurants"]
        errors = data.get("errors", [])
        if not isinstance(restaurants, list) or not isinstance(errors, list):
            return None
        return rec, restaurants, errors
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    date = args.date

    load_env_files()
    cfg = load_config()  # 키가 없으면 여기서 종료 코드 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data_path = RESULTS_DIR / f"{date}_data.json"
    md_path = RESULTS_DIR / f"{date}_travel_plan.md"
    html_path = RESULTS_DIR / f"{date}_travel_plan.html"

    errors: list[dict] = []
    cached = load_cache(data_path) if args.use_cache and data_path.is_file() else None

    if cached:
        rec, restaurants, prev_errors = cached
        # 이전 실행의 1~2단계 오류는 유지하고, 리포트 오류는 새로 기록한다.
        errors = [x for x in prev_errors if isinstance(x, dict) and x.get("step") != "report"]
        log(f"[1/3] 1차 추천: 저장된 데이터 사용 ({data_path.as_posix()})")
        log(f'  - recommended_city: "{rec["recommended_city"]}"')
        log("[2/3] 맛집 검색: 저장된 데이터 사용")
        log(f"  - 맛집 {len(restaurants)}곳")
    else:
        log("[1/3] 1차 추천 생성 중(LLM)...")
        rec = get_recommendation(cfg, date, errors)
        log(f'  - recommended_city: "{rec["recommended_city"]}"')

        log("[2/3] 맛집 검색 중(지도/장소 API)...")
        restaurants = search_restaurants(cfg, rec["recommended_city"], errors)

    log("[3/3] 최종 리포트 생성 중(LLM)...")
    content = write_report_content(cfg, date, rec, restaurants, errors)

    data = redact_obj({"date": date, "recommendation": rec, "restaurants": restaurants, "errors": errors})
    content = redact_obj(content)
    save_text(data_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    save_text(md_path, render_markdown(date, data["recommendation"], data["restaurants"], content, data["errors"]))
    save_text(html_path, render_html(date, data["recommendation"], data["restaurants"], content, data["errors"]))

    log("")
    log(f"완료! {md_path.as_posix()} 를 확인하세요.")
    log(f"  - 원본 데이터: {data_path.as_posix()}")
    log(f"  - HTML 리포트: {html_path.as_posix()}")
    if errors:
        log(f"  - 오류 {len(errors)}건이 리포트의 '오류 요약(errors)' 절에 기록되었습니다.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log_err("\n중단되었습니다.")
        sys.exit(130)
