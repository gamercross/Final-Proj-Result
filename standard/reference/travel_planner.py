"""기준 v1을 지키는 가장 작은 구현 — 수용 시험이 맞는지 확인하는 용도(비교 대상이 아니다).

표준 라이브러리만 쓴다. 실행: python travel_planner.py -date 2026-03-15
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SECTIONS = ["추천 지역", "추천 이유", "날씨 요약", "행사/축제", "맛집 추천", "1일 일정 제안", "오류 요약(errors)"]


def load_env_file():
    p = Path.cwd() / ".env"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*)", line)
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip().strip('"')


def hide(text: str) -> str:
    for k in ("OPENAI_API_KEY", "KAKAO_REST_API_KEY"):
        v = os.environ.get(k)
        if v:
            text = text.replace(v, "***")
    return text


def http(method, url, headers, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(prompt: str) -> str:
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    r = http("POST", f"{base}/chat/completions", {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
             {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "messages": [{"role": "user", "content": prompt}]})
    return r["choices"][0]["message"]["content"]


def parse_reco(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    d = json.loads(m.group(0)) if m else None
    ok = isinstance(d, dict) and all(isinstance(d.get(k), str) and d[k] for k in ("recommended_city", "weather", "reason")) \
        and isinstance(d.get("events"), list) and 1 <= len(d["events"]) <= 3
    if not ok:
        raise ValueError("필수 키가 없거나 모양이 다름")
    return d


def recommend(date, errors):
    prompt = (f"날짜 {date}에 국내 여행하기 좋은 도시 하나를 JSON으로만 답하세요. "
              '키: recommended_city(문자열), weather(문자열), events(문자열 1~3개 배열), reason(2~4문장).')
    for attempt in (1, 2):
        try:
            return parse_reco(chat(prompt if attempt == 1 else prompt + " 다른 글 없이 JSON 하나만."))
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            errors.append({"step": "recommendation", "type": "PARSE_ERROR", "message": hide(str(e))})
        except (urllib.error.URLError, OSError) as e:
            errors.append({"step": "recommendation", "type": "API_ERROR", "message": hide(str(e))})
            return None
    return None


def places(city, errors):
    base = os.environ.get("KAKAO_BASE_URL", "https://dapi.kakao.com").rstrip("/")
    q = urllib.parse.urlencode({"query": f"{city} 맛집", "size": 5})
    try:
        r = http("GET", f"{base}/v2/local/search/keyword.json?{q}", {"Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}"})
    except urllib.error.HTTPError as e:
        typ = "AUTH_ERROR" if e.code in (401, 403) else "QUOTA_ERROR" if e.code == 429 else "API_ERROR"
        errors.append({"step": "place_search", "type": typ, "message": f"HTTP {e.code}"})
        return []
    except (urllib.error.URLError, OSError) as e:
        errors.append({"step": "place_search", "type": "NETWORK_ERROR", "message": hide(str(e))})
        return []
    docs = r.get("documents") or []
    if not docs:
        errors.append({"step": "place_search", "type": "EMPTY_RESULT", "message": f"0 results for query={city} 맛집"})
    return [{"name": d.get("place_name", ""), "address": d.get("road_address_name") or d.get("address_name", ""),
             "category": d.get("category_name", ""), "url": d.get("place_url", ""),
             "x": float(d.get("x") or 0), "y": float(d.get("y") or 0)} for d in docs[:5]]


def report(date, reco, shops, errors):
    day = {"오전": f"{reco['recommended_city']} 둘러보기", "오후": "", "저녁": ""}
    try:
        text = chat(f"{reco['recommended_city']} 1일 여행 일정을 오전/오후/저녁 세 줄로. 맛집: {', '.join(s['name'] for s in shops) or '없음'}")
        for k in day:
            m = re.search(rf"{k}\s*[:：]\s*(.+)", text)
            if m:
                day[k] = m.group(1).strip()
    except (urllib.error.URLError, OSError, KeyError) as e:
        errors.append({"step": "report", "type": "API_ERROR", "message": hide(str(e))})
    for k in day:
        day[k] = day[k] or (f"{shops[0]['name']}에서 식사" if shops else "자유 일정")
    body = {
        "추천 지역": [reco["recommended_city"]],
        "추천 이유": [reco["reason"]],
        "날씨 요약": [reco["weather"]],
        "행사/축제": [f"- {e}" for e in reco["events"]],
        "맛집 추천": [f"- {s['name']} ({s['category']}) — {s['address']} {s['url']}" for s in shops] or ["- 데이터 없음"],
        "1일 일정 제안": [f"- {k}: {v}" for k, v in day.items()],
        "오류 요약(errors)": [f"- {e['step']} · {e['type']}: {e['message']}" for e in errors] or ["- 없음"],
    }
    md = [f"# {date} 국내 여행 추천 리포트", ""]
    for s in SECTIONS:
        md += [f"## {s}", *body[s], ""]
    h = [f"<!doctype html><html lang='ko'><meta charset='utf-8'><title>{date} 국내 여행 추천 리포트</title><body>",
         f"<h1>{html.escape(date)} 국내 여행 추천 리포트</h1>"]
    for s in SECTIONS:
        h += [f"<h2>{html.escape(s)}</h2>", "<ul>" + "".join(f"<li>{html.escape(x.lstrip('- '))}</li>" for x in body[s]) + "</ul>"]
    return "\n".join(md), "\n".join(h + ["</body></html>"])


def main():
    def day(v):
        try:
            dt.date.fromisoformat(v)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise ValueError
            return v
        except ValueError:
            raise argparse.ArgumentTypeError("YYYY-MM-DD 모양이어야 합니다")

    ap = argparse.ArgumentParser(description="국내 여행 추천")
    ap.add_argument("-date", required=True, type=day)
    date = ap.parse_args().date
    load_env_file()
    missing = [k for k in ("OPENAI_API_KEY", "KAKAO_REST_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f"키가 없습니다: {', '.join(missing)} — export {missing[0]}=... 또는 .env 파일에 적으세요.")
        return 1
    errors = []
    print("[1/3] 1차 추천 생성 중(LLM)...")
    reco = recommend(date, errors)
    if not reco:
        print("1차 추천을 받지 못해 멈춥니다.")
        return 1
    print(f"  - recommended_city: {reco['recommended_city']}")
    print("[2/3] 맛집 검색 중(지도 API)...")
    shops = places(reco["recommended_city"], errors)
    print(f"  - 맛집 {len(shops)}곳")
    print("[3/3] 최종 리포트 생성 중(LLM)...")
    md, page = report(date, reco, shops, errors)
    out = Path("results")
    out.mkdir(exist_ok=True)
    (out / f"{date}_data.json").write_text(json.dumps({"date": date, "recommendation": reco, "restaurants": shops, "errors": errors},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{date}_travel_plan.md").write_text(md, encoding="utf-8")
    (out / f"{date}_travel_plan.html").write_text(page, encoding="utf-8")
    print(f"완료! results/{date}_travel_plan.md · results/{date}_travel_plan.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
