"""Kakao Local 키워드 검색으로 맛집을 찾는다.

GET https://dapi.kakao.com/v2/local/search/keyword.json?query=...&category_group_code=FD6
헤더: Authorization: KakaoAK {REST_API_KEY}
"""

from __future__ import annotations

from typing import Any, Protocol

from .errors import AUTH_ERROR, EMPTY_RESULT, PARSE_ERROR, QUOTA_ERROR, APIError, ErrorLog, request_json

ERROR_HINTS = {
    AUTH_ERROR: "인증 실패. REST API 키 값과, 카카오 개발자 콘솔에서 '카카오맵' 사용 설정이 켜져 있는지 확인하세요.",
    QUOTA_ERROR: "호출 한도 초과. 잠시 후 다시 시도하세요.",
}


class PlaceClient(Protocol):
    name: str

    def search_restaurants(self, city: str, size: int) -> list[dict[str, Any]]: ...


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_kakao(doc: dict[str, Any]) -> dict[str, Any]:
    x, y = _to_float(doc.get("x")), _to_float(doc.get("y"))
    category = doc.get("category_name") or ""
    return {
        "name": doc.get("place_name") or "",
        "address": doc.get("road_address_name") or doc.get("address_name") or "",
        "category": category.split(" > ")[-1] if category else "",
        "category_full": category,
        "phone": doc.get("phone") or "",
        "url": doc.get("place_url") or "",
        "x": x,  # 경도(lng)
        "y": y,  # 위도(lat)
        "lat": y,
        "lng": x,
    }


class KakaoPlaces:
    URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
    FOOD_CATEGORY = "FD6"  # 카카오 카테고리 코드: 음식점

    def __init__(self, api_key: str, timeout: float = 15.0):
        self.name = "kakao-local"
        self._api_key = api_key
        self.timeout = timeout

    def search_restaurants(self, city: str, size: int = 5) -> list[dict[str, Any]]:
        data = request_json(
            "GET",
            self.URL,
            headers={"Authorization": f"KakaoAK {self._api_key}"},
            params={
                "query": f"{city} 맛집",
                "category_group_code": self.FOOD_CATEGORY,
                "size": max(1, min(size, 15)),  # 카카오 size 허용 범위 1~15
                "sort": "accuracy",
            },
            timeout=self.timeout,
        )
        docs = data.get("documents") if isinstance(data, dict) else None
        if not isinstance(docs, list):
            raise APIError(PARSE_ERROR, "Kakao 응답에 documents 배열이 없습니다")
        return [normalize_kakao(d) for d in docs if isinstance(d, dict)]


def search_all(
    client: PlaceClient, cities: list[str], size: int, errors: ErrorLog
) -> list[dict[str, Any]]:
    """도시별로 맛집을 검색. 실패해도 예외를 밖으로 던지지 않고 '데이터 없음'으로 기록한다."""
    results = []
    for city in cities:
        query = f"{city} 맛집"
        entry: dict[str, Any] = {"city": city, "query": query, "status": "ok", "items": []}
        prefix = f"    - [{city}] " if len(cities) > 1 else "    - "
        try:
            items = client.search_restaurants(city, size)
        except APIError as exc:
            entry["status"] = "error"
            entry["error"] = exc.type
            errors.add("place_search", exc.type, f"{exc.message} (query={query})")
            print(f"{prefix}오류: {exc.type} - {exc.message}")
            if exc.type in ERROR_HINTS:
                print(f"      {ERROR_HINTS[exc.type]}")
            print("      맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.")
        else:
            if items:
                entry["items"] = items
                print(f"{prefix}맛집 {len(items)}곳 검색 완료")
            else:
                entry["status"] = "empty"
                errors.add("place_search", EMPTY_RESULT, f"0 results for query={query}")
                print(f"{prefix}검색 결과 0건 (재시도하지 않고 다음 단계로 진행)")
        results.append(entry)
    return results
