"""6단계 확인 — 맛집 찾기: 지역을 넣으면 맛집 목록이 나와야 해요.

실제 지도 API를 부르지 않고 requests.get 을 가짜로 바꿔 확인한다.
실행: python -m unittest discover -s tests -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import travel_planner as tp  # noqa: E402

DOC = {"place_name": "가짜 식당", "road_address_name": "가짜 도로명 주소", "address_name": "가짜 지번 주소",
       "category_name": "음식점 > 한식", "place_url": "http://place.example/1", "x": "127.1", "y": "37.5"}
GOOD_REC = {"recommended_city": "가짜도시", "weather": "가짜 날씨", "events": ["가짜 행사"], "reason": "가짜 이유."}


def map_reply(docs=None, status=200):
    """지도 응답 하나를 흉내 낸다."""
    resp = mock.Mock()
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status}", response=resp)
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = {"documents": docs if docs is not None else []}
    return resp


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class SearchRestaurantsTest(unittest.TestCase):
    def search(self, **get_kwargs):
        errors = []
        with mock.patch.object(tp.requests, "get", **get_kwargs) as get, redirect_stderr(io.StringIO()):
            result = tp.search_restaurants("가짜도시", errors)
        return result, errors, get

    # 상황: 지역 '가짜도시', 지도가 5곳을 준다 → 할 일: 맛집 찾기 → 기대: 맛집 5곳 목록, errors 없음
    def test_city_gives_restaurant_list(self):
        docs = [{**DOC, "place_name": f"가짜 식당 {i}"} for i in range(1, 6)]
        result, errors, get = self.search(return_value=map_reply(docs))
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], {"name": "가짜 식당 1", "address": "가짜 도로명 주소", "category": "음식점 > 한식",
                                     "url": "http://place.example/1", "x": 127.1, "y": 37.5})
        self.assertEqual(errors, [])
        self.assertEqual(get.call_count, 1)

    # 막을 일: 지도 서비스에 나가는 것은 지역 이름(+ 검색어)과 개수뿐이다
    def test_only_city_goes_out(self):
        _, _, get = self.search(return_value=map_reply([DOC]))
        params = get.call_args.kwargs["params"]
        self.assertEqual(set(params), {"query", "size"})
        self.assertIn("가짜도시", params["query"])
        self.assertEqual(params["size"], tp.PLACE_COUNT)
        self.assertTrue(get.call_args.kwargs["headers"]["Authorization"].startswith("KakaoAK "))

    # 도로명 주소가 없으면 지번 주소, 좌표가 없거나 숫자가 아니면 None (멈추지 않는다)
    def test_missing_fields_do_not_stop(self):
        odd = [{**DOC, "road_address_name": ""}, {"place_name": "좌표 없음"}, {**DOC, "x": "abc", "y": ""}]
        result, errors, _ = self.search(return_value=map_reply(odd))
        self.assertEqual(result[0]["address"], "가짜 지번 주소")
        self.assertEqual(result[1], {"name": "좌표 없음", "address": "", "category": "", "url": "", "x": None, "y": None})
        self.assertEqual((result[2]["x"], result[2]["y"]), (None, None))
        self.assertEqual(errors, [])

    # 상황: 0건 → 기대: 빈 목록 + EMPTY_RESULT
    def test_zero_results(self):
        result, errors, _ = self.search(return_value=map_reply([]))
        self.assertEqual(result, [])
        self.assertEqual(errors, [{"step": "place_search", "type": "EMPTY_RESULT",
                                   "message": "0 results for query=가짜도시 맛집"}])

    # 상황: 401/403 · 429 · 네트워크 오류 → 기대: 빈 목록 + 알맞은 type (기준 7)
    def test_failures_are_classified(self):
        cases = [
            ({"return_value": map_reply(status=401)}, "AUTH_ERROR", "HTTP 401"),
            ({"return_value": map_reply(status=403)}, "AUTH_ERROR", "HTTP 403"),
            ({"return_value": map_reply(status=429)}, "QUOTA_ERROR", "HTTP 429"),
            ({"side_effect": requests.ConnectionError("x")}, "NETWORK_ERROR", "ConnectionError"),
            ({"side_effect": requests.Timeout("x")}, "NETWORK_ERROR", "Timeout"),
        ]
        for kwargs, kind, message in cases:
            with self.subTest(kind=kind, message=message):
                result, errors, get = self.search(**kwargs)
                self.assertEqual(result, [])
                self.assertEqual(errors, [{"step": "place_search", "type": kind, "message": message}])
                self.assertEqual(get.call_count, 1)  # 다시 요청하지 않는다

    # 키 값은 errors 에 들어가지 않는다
    def test_key_not_in_errors(self):
        with mock.patch.dict(os.environ, {"KAKAO_REST_API_KEY": "SECRET-KEY-123"}):
            _, errors, _ = self.search(side_effect=requests.ConnectionError("SECRET-KEY-123"))
        self.assertNotIn("SECRET-KEY-123", json.dumps(errors))


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class MainContinuesTest(unittest.TestCase):
    def run_main(self, map_resp):
        llm = mock.Mock()
        llm.raise_for_status.return_value = None
        llm.json.return_value = {"choices": [{"message": {"content": json.dumps(GOOD_REC, ensure_ascii=False)}}]}
        # 두 번째 LLM 부름은 리포트 글이다(리포트 기능, tests/test_report.py)
        report = mock.Mock()
        report.raise_for_status.return_value = None
        report.json.return_value = {"choices": [{"message": {"content": json.dumps(
            {"reason_summary": "가짜 요약.", "itinerary": {"morning": "가", "afternoon": "나", "evening": "다"}},
            ensure_ascii=False)}}]}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tp, "RESULTS_DIR", Path(tmp)), mock.patch.object(tp, "load_dotenv"), \
             mock.patch.object(tp.requests, "post", side_effect=[llm, report]), \
             mock.patch.object(tp.requests, "get", return_value=map_resp), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            tp.main(["-date", "2026-03-15"])
            data = json.loads((Path(tmp) / "2026-03-15_data.json").read_text(encoding="utf-8"))
            report = (Path(tmp) / "2026-03-15_travel_plan.md").read_text(encoding="utf-8")
        return data, report, out.getvalue() + err.getvalue()

    # 상황: 추천 지역이 정해지고 지도가 맛집을 준다 → 기대: 결과 파일에 그 지역의 맛집 목록
    def test_restaurants_reach_results(self):
        data, report, out = self.run_main(map_reply([DOC]))
        self.assertEqual(data["restaurants"][0]["name"], "가짜 식당")
        self.assertIn("가짜 식당", report)
        self.assertIn("맛집 1곳 검색 완료", out)

    # 상황: 지도 인증 실패(401) → 기대: 멈추지 않고 '데이터 없음' + AUTH_ERROR + 안내
    def test_auth_failure_continues(self):
        data, report, out = self.run_main(map_reply(status=401))
        self.assertEqual(data["restaurants"], [])
        self.assertEqual(data["errors"], [{"step": "place_search", "type": "AUTH_ERROR", "message": "HTTP 401"}])
        self.assertIn("## 맛집 추천\n- 데이터 없음", report)
        self.assertIn("인증 실패(401)", out)


if __name__ == "__main__":
    unittest.main()
