"""국내 여행 추천 프로그램.

흐름: 여행 날짜 → (LLM) 추천 지역 → (Kakao Local) 맛집 → (LLM) 리포트(.md · .html) + 원본 데이터(.json)
키는 환경변수 또는 .env 에서만 읽는다. 코드에 키를 쓰지 않는다.
"""
import argparse
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

REQUIRED_KEYS = ["OPENAI_API_KEY", "KAKAO_REST_API_KEY"]
RECOMMEND_KEYS = ["recommended_city", "weather", "events", "reason"]
PLACE_COUNT = 5  # 기준 v1 3번: 맛집 5곳
TIMEOUT_SEC = 20  # 임시값 — README '정할 것' 참고
RESULTS_DIR = Path("results")


# ① 입력 -------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="국내 여행 추천 프로그램")
    parser.add_argument("-date", "--date", required=True, help='여행 날짜 "YYYY-MM-DD"')
    args = parser.parse_args(argv)
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.print_usage(sys.stderr)
        print(f"오류: 날짜 형식이 YYYY-MM-DD 가 아닙니다: {args.date}", file=sys.stderr)
        sys.exit(2)
    return args


def check_keys():
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        print("오류: API 키가 설정되지 않았습니다: " + ", ".join(missing), file=sys.stderr)
        print("설정 방법: .env.example 을 .env 로 복사해 값을 채우거나,", file=sys.stderr)
        print("          export " + "=... / export ".join(missing) + "=...", file=sys.stderr)
        sys.exit(1)


# ② AI가 좋은 지역 추천 --------------------------------------------------
def parse_recommendation(content):
    """LLM이 준 글을 1차 추천으로 읽는다(기준 6). 읽지 못하거나 키 · 타입이 어긋나면 ValueError."""
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("추천 JSON을 읽지 못했습니다")
    if not isinstance(data, dict):
        raise ValueError("추천 JSON이 객체가 아닙니다")
    missing = [k for k in RECOMMEND_KEYS if k not in data]
    if missing:
        raise ValueError(f"추천 JSON에 키가 없습니다: {missing}")
    city = data["recommended_city"]
    if not isinstance(city, str) or not city.strip():
        raise ValueError("recommended_city 가 비었거나 글이 아닙니다")
    for k in ("weather", "reason"):
        if not isinstance(data[k], str):
            raise ValueError(f"{k} 가 글이 아닙니다")
    events = data["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 3 or not all(isinstance(e, str) for e in events):
        raise ValueError("events 는 글 1~3개여야 합니다")
    return {k: data[k] for k in RECOMMEND_KEYS}


def recommend_city(date):
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = (
        f"여행 날짜 {date}에 국내에서 여행하기 좋은 지역 1곳을 추천해 줘. "
        "JSON 객체만 출력해. 키: recommended_city(문자열), weather(문자열, 그 시기 일반적 날씨), "
        "events(문자열 배열 1~3개, 행사/축제 후보), reason(문자열, 추천 근거 2~4문장)."
    )
    retry_note = " 필수 키만 다시 JSON으로 출력해."
    # 기준 6: 읽지 못하거나 키가 빠지면 딱 한 번 다시 요청, 또 실패하면 ValueError(→ main 에서 종료 코드 1).
    # 밖으로 나가는 것은 날짜가 담긴 이 프롬프트뿐이다.
    for attempt in range(2):
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt + (retry_note if attempt else "")}],
                  "response_format": {"type": "json_object"}},
            timeout=TIMEOUT_SEC,
        )
        resp.raise_for_status()  # 네트워크 · HTTP 오류는 다시 요청하지 않는다(README '정할 것')
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            return parse_recommendation(content)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            if attempt:
                raise ValueError(f"다시 요청해도 추천을 읽지 못했습니다: {e}")
            print(f"  - 추천을 읽지 못해 한 번 다시 요청합니다 ({e})", file=sys.stderr)


# ③ 지도로 맛집 찾기 -----------------------------------------------------
def _to_number(value):
    """좌표 글을 숫자로. 없거나 숫자가 아니면 None (기준 7: x · y 는 숫자, 가능한 경우)."""
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _classify_place_error(e):
    """지도 오류를 기준 7의 type 으로 나눈다. message 에는 상태 코드나 예외 이름만 담는다(키가 섞이지 않게)."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return "AUTH_ERROR", f"HTTP {status}", f"인증 실패({status}). 키 설정을 확인하세요."
    if status == 429:
        return "QUOTA_ERROR", "HTTP 429", "요청 한도 초과(429). 잠시 뒤 다시 시도하세요."
    if status is not None:  # 그 밖의 HTTP 오류 — 기준에 따로 없어 NETWORK_ERROR 로 둔다(README '정할 것')
        return "NETWORK_ERROR", f"HTTP {status}", f"지도 서비스 오류({status})."
    return "NETWORK_ERROR", type(e).__name__, f"네트워크 오류({type(e).__name__})."


def search_restaurants(city, errors):
    """지역 이름으로 맛집을 찾는다(기준 7). 어떤 실패에도 멈추지 않고 빈 목록 + errors 에 남긴다."""
    base = os.getenv("KAKAO_BASE_URL", "https://dapi.kakao.com").rstrip("/")
    query = f"{city} 맛집"  # 임시 검색어 — README '정할 것'
    try:
        # 밖으로 나가는 것은 지역 이름(+ 검색어)과 개수뿐이다.
        resp = requests.get(
            f"{base}/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}"},
            params={"query": query, "size": PLACE_COUNT},
            timeout=TIMEOUT_SEC,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])  # 읽지 못한 응답은 requests.JSONDecodeError(RequestException)
    except requests.RequestException as e:
        kind, message, hint = _classify_place_error(e)
        print(f"  - 오류: {hint}", file=sys.stderr)
        errors.append({"step": "place_search", "type": kind, "message": message})
        return []
    if not docs:
        errors.append({"step": "place_search", "type": "EMPTY_RESULT", "message": f"0 results for query={query}"})
    return [
        {"name": d.get("place_name", ""), "address": d.get("road_address_name") or d.get("address_name", ""),
         "category": d.get("category_name", ""), "url": d.get("place_url", ""),
         "x": _to_number(d.get("x")), "y": _to_number(d.get("y"))}
        for d in docs
    ]


# ④ 여행 리포트 ---------------------------------------------------------
REPORT_KEYS = ["reason_summary", "itinerary"]
ITINERARY_PARTS = [("morning", "오전"), ("afternoon", "오후"), ("evening", "저녁")]
NO_DATA = "데이터 없음"


def parse_report(content):
    """리포트 LLM이 준 글을 읽는다. 읽지 못하거나 키 · 타입이 어긋나면 ValueError."""
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("리포트 JSON을 읽지 못했습니다")
    if not isinstance(data, dict) or any(k not in data for k in REPORT_KEYS):
        raise ValueError("리포트 JSON에 키가 없습니다")
    if not isinstance(data["reason_summary"], str):
        raise ValueError("reason_summary 가 글이 아닙니다")
    plan = data["itinerary"]
    if not isinstance(plan, dict) or not all(isinstance(plan.get(k), str) for k, _ in ITINERARY_PARTS):
        raise ValueError("itinerary 는 morning · afternoon · evening 글이어야 합니다")
    return {"reason_summary": data["reason_summary"], "itinerary": {k: plan[k] for k, _ in ITINERARY_PARTS}}


def write_report(date, rec, restaurants, errors):
    """최종 리포트 글(추천 이유 요약 + 1일 일정)을 LLM으로 쓴다(기준 8).

    실패하면 errors 에 step "report" 를 남기고 None — main 은 가진 데이터로 리포트를 만든다.
    밖으로 나가는 것은 날짜와 모인 결과(1차 추천 · 맛집 이름/주소/분류)뿐이다.
    """
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    facts = {"date": date, **{k: rec[k] for k in RECOMMEND_KEYS},
             "restaurants": [{"name": r["name"], "address": r["address"], "category": r["category"]}
                             for r in restaurants]}
    prompt = (
        "아래 여행 정보로 국내 여행 리포트에 들어갈 글을 써 줘. JSON 객체만 출력해. "
        "키: reason_summary(문자열, 추천 이유 요약), "
        "itinerary(객체: morning · afternoon · evening 각각 문자열, 1일 일정 제안. 맛집이 있으면 그중에서 골라 넣어).\n"
        + json.dumps(facts, ensure_ascii=False)
    )
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "response_format": {"type": "json_object"}},
            timeout=TIMEOUT_SEC,
        )
        resp.raise_for_status()
    except requests.RequestException as e:  # 다시 요청하지 않는다(README '정할 것')
        kind, message, _ = _classify_place_error(e)  # 상태 코드나 예외 이름만 담는다(키가 섞이지 않게)
        print(f"  - 오류: 리포트 글을 받지 못했습니다({message}). 가진 데이터로 만듭니다.", file=sys.stderr)
        errors.append({"step": "report", "type": kind, "message": message})
        return None
    try:
        return parse_report(resp.json()["choices"][0]["message"]["content"])
    except (ValueError, KeyError, IndexError, TypeError) as e:
        message = str(e) if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError) else type(e).__name__
        print(f"  - 오류: 리포트 글을 읽지 못했습니다({message}). 가진 데이터로 만듭니다.", file=sys.stderr)
        errors.append({"step": "report", "type": "PARSE_ERROR", "message": message})
        return None


def report_sections(rec, restaurants, errors, written):
    """기준 10 순서의 절. 절 제목은 프로그램이 보장한다(기준 8). (제목, 글 줄 또는 목록 여부, 줄들)"""
    plan = (written or {}).get("itinerary") or {}
    return [
        ("추천 지역", False, [rec["recommended_city"]]),
        ("추천 이유", False, [(written or {}).get("reason_summary") or rec["reason"]]),
        ("날씨 요약", False, [rec["weather"]]),
        ("행사/축제", True, list(rec["events"]) or [NO_DATA]),
        ("맛집 추천", True, [f"{r['name']} — {r['address']} ({r['category']}) {r['url']}".rstrip()
                          for r in restaurants] or [NO_DATA]),
        ("1일 일정 제안", True, [f"{label}: {plan.get(k) or NO_DATA}" for k, label in ITINERARY_PARTS]),
        ("오류 요약(errors)", True, [f"{e['step']} · {e['type']} · {e['message']}" for e in errors] or ["없음"]),
    ]


def build_report(date, rec, restaurants, errors, written=None):
    lines = [f"# {date} 국내 여행 추천 리포트"]
    for title, is_list, items in report_sections(rec, restaurants, errors, written):
        lines += ["", f"## {title}"] + ([f"- {i}" for i in items] if is_list else items)
    return "\n".join(lines) + "\n"


def build_html(date, rec, restaurants, errors, written=None):
    """파일 하나로 열리는 HTML(기준 9 · 11) — 바깥 스크립트 · 스타일 · 글꼴을 부르지 않고, 바깥 글은 이스케이프."""
    title = html.escape(f"{date} 국내 여행 추천 리포트")
    parts = ["<!DOCTYPE html>", '<html lang="ko">', "<head>", '<meta charset="utf-8">',
             f"<title>{title}</title>", "</head>", "<body>", f"<h1>{title}</h1>"]
    for name, is_list, items in report_sections(rec, restaurants, errors, written):
        parts.append(f"<h2>{html.escape(name)}</h2>")
        if is_list:
            parts += ["<ul>"] + [f"<li>{html.escape(i)}</li>" for i in items] + ["</ul>"]
        else:
            parts += [f"<p>{html.escape(i)}</p>" for i in items]
    parts += ["</body>", "</html>"]
    return "\n".join(parts) + "\n"


def main(argv=None):
    load_dotenv()
    args = parse_args(argv)
    check_keys()
    errors = []

    print("[1/3] 1차 추천 생성 중(LLM)...")
    try:
        rec = recommend_city(args.date)  # 읽지 못하면 안에서 딱 한 번 다시 요청
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"  - 오류: 추천을 받지 못했습니다 ({type(e).__name__})", file=sys.stderr)
        sys.exit(1)
    print(f'  - recommended_city: "{rec["recommended_city"]}"')

    print("[2/3] 맛집 검색 중(지도/장소 API)...")
    restaurants = search_restaurants(rec["recommended_city"], errors)
    print(f"  - 맛집 {len(restaurants)}곳 검색 완료" if restaurants else "  - 맛집 없음, '데이터 없음'으로 계속합니다")

    print("[3/3] 최종 리포트 생성 중(LLM)...")
    written = write_report(args.date, rec, restaurants, errors)  # 실패하면 errors 에 남기고 가진 데이터로
    RESULTS_DIR.mkdir(exist_ok=True)
    data_path = RESULTS_DIR / f"{args.date}_data.json"
    md_path = RESULTS_DIR / f"{args.date}_travel_plan.md"
    html_path = RESULTS_DIR / f"{args.date}_travel_plan.html"
    data_path.write_text(json.dumps({"date": args.date, "recommendation": rec, "restaurants": restaurants,
                                     "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_report(args.date, rec, restaurants, errors, written), encoding="utf-8")
    html_path.write_text(build_html(args.date, rec, restaurants, errors, written), encoding="utf-8")
    print("  - 리포트 생성 완료" if written else "  - 리포트 생성 완료(LLM 글 없이 가진 데이터로)")
    print()
    print(f"완료! {md_path} 를 확인하세요. (HTML: {html_path} · 원본 데이터: {data_path})")

if __name__ == "__main__":
    main()
