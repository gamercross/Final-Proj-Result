"""여행 날짜 → AI 지역 추천 → 지도 서비스 맛집 → 1일 일정 리포트."""
import json
import os
from datetime import date

import requests
from openai import OpenAI

OPENAI_MODEL = "gpt-4o-mini"
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
RESTAURANT_COUNT = 5


class MissingKeyError(Exception):
    pass


class InputError(Exception):
    pass


def _key(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingKeyError(f"{name}가 없어요 — .env 파일에 {name}=... 를 적어 주세요.")
    return value


def parse_date(text):
    text = (text or "").strip()
    if not text:
        raise InputError("여행 날짜를 넣어 주세요.")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise InputError("날짜는 YYYY-MM-DD 모양으로 넣어 주세요.")


def recommend_region(travel_date, client=None):
    """AI에게 그 시기에 가기 좋은 국내 지역 하나를 받는다. 날짜만 보낸다."""
    client = client or OpenAI(api_key=_key("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "너는 국내 여행 추천가야. JSON으로만 답해."},
            {"role": "user", "content": (
                f"{travel_date.isoformat()}에 여행하기 좋은 대한민국 지역 한 곳을 추천해 줘. "
                '{"region": "지역 이름(시·군 단위)", "reason": "그 시기에 좋은 까닭 한두 문장"} 모양으로.'
            )},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    region = str(data.get("region", "")).strip()
    if not region:
        raise ValueError("AI 답에 지역 이름이 없어요.")
    return {"region": region, "reason": str(data.get("reason", "")).strip()}


def search_restaurants(region, http_get=None):
    """카카오 로컬 키워드 검색으로 그 지역 음식점을 찾는다. 지역 이름만 보낸다."""
    resp = (http_get or requests.get)(
        KAKAO_URL,
        headers={"Authorization": f"KakaoAK {_key('KAKAO_REST_API_KEY')}"},
        params={"query": f"{region} 맛집", "category_group_code": "FD6", "size": RESTAURANT_COUNT},
        timeout=10,
    )
    resp.raise_for_status()
    return [
        {
            "name": d.get("place_name", ""),
            "category": d.get("category_name", ""),
            "address": d.get("road_address_name") or d.get("address_name", ""),
            "phone": d.get("phone", ""),
            "url": d.get("place_url", ""),
        }
        for d in resp.json().get("documents", [])
    ]


def build_itinerary(region, restaurants):
    lunch = restaurants[0]["name"] if restaurants else "현지 식당"
    dinner = restaurants[1]["name"] if len(restaurants) > 1 else lunch
    return [
        {"time": "10:00", "plan": f"{region} 도착, 둘러보기"},
        {"time": "12:00", "plan": f"점심 — {lunch}"},
        {"time": "14:00", "plan": f"{region} 명소 구경"},
        {"time": "18:00", "plan": f"저녁 — {dinner}"},
    ]


def make_report(date_text, client=None, http_get=None):
    travel_date = parse_date(date_text)
    # 열쇠 둘을 먼저 확인해, 하나만 있을 때 AI만 불리고 멈추는 일을 막는다.
    _key("OPENAI_API_KEY")
    _key("KAKAO_REST_API_KEY")
    rec = recommend_region(travel_date, client=client)
    restaurants = search_restaurants(rec["region"], http_get=http_get)
    return {
        "date": travel_date.isoformat(),
        "region": rec["region"],
        "reason": rec["reason"],
        "restaurants": restaurants,
        "itinerary": build_itinerary(rec["region"], restaurants),
    }
