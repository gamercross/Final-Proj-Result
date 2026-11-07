"""6단계 확인 — 지역 추천: 날짜를 넣으면 지역 이름이 나와야 해요.

실제 API를 부르지 않고 requests.post 를 가짜로 바꿔 확인한다.
실행: python -m unittest discover -s tests -v
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import travel_planner as tp  # noqa: E402

GOOD = {"recommended_city": "가짜도시", "weather": "가짜 날씨", "events": ["가짜 행사"], "reason": "가짜 이유입니다."}


def llm_reply(content):
    """LLM 응답 하나를 흉내 낸다. content 가 dict면 JSON 글로 바꾼다."""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    resp = mock.Mock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class RecommendCityTest(unittest.TestCase):
    # 상황: 날짜를 넣고 AI가 올바른 JSON을 준다 → 할 일: 추천 받기 → 기대: 지역 이름이 나온다
    def test_date_gives_city_name(self):
        with mock.patch.object(tp.requests, "post", return_value=llm_reply(GOOD)) as post:
            rec = tp.recommend_city("2026-03-15")
        self.assertEqual(rec["recommended_city"], "가짜도시")
        self.assertEqual(post.call_count, 1)

    # 막을 일: AI에게 나가는 것은 날짜가 담긴 글뿐이다
    def test_only_date_goes_out(self):
        with mock.patch.object(tp.requests, "post", return_value=llm_reply(GOOD)) as post:
            tp.recommend_city("2026-03-15")
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertIn("2026-03-15", messages[0]["content"])

    # 상황: 첫 응답을 읽지 못한다 → 할 일: 추천 받기 → 기대: 딱 한 번 다시 요청해 지역 이름이 나온다
    def test_unreadable_then_good_retries_once(self):
        with mock.patch.object(tp.requests, "post", side_effect=[llm_reply("JSON 아님"), llm_reply(GOOD)]) as post:
            rec = tp.recommend_city("2026-03-15")
        self.assertEqual(rec["recommended_city"], "가짜도시")
        self.assertEqual(post.call_count, 2)

    # 상황: 첫 응답에 키가 빠진다 → 기대: 딱 한 번 다시 요청
    def test_missing_key_then_good_retries_once(self):
        partial = {k: v for k, v in GOOD.items() if k != "reason"}
        with mock.patch.object(tp.requests, "post", side_effect=[llm_reply(partial), llm_reply(GOOD)]) as post:
            rec = tp.recommend_city("2026-03-15")
        self.assertEqual(rec["reason"], GOOD["reason"])
        self.assertEqual(post.call_count, 2)

    # 상황: 두 번 다 실패 → 기대: 세 번째는 부르지 않고 ValueError (main 이 종료 코드 1로 바꾼다)
    def test_two_failures_raise_no_third_call(self):
        with mock.patch.object(tp.requests, "post", side_effect=[llm_reply("x"), llm_reply("y"), llm_reply(GOOD)]) as post:
            with self.assertRaises(ValueError):
                tp.recommend_city("2026-03-15")
        self.assertEqual(post.call_count, 2)

    # 기준 6의 타입: 글 · 글 · 글 1~3개 · 글. 어긋나면 '읽지 못함'과 같이 다시 요청한다
    def test_wrong_types_are_rejected(self):
        bad_cases = [
            {**GOOD, "recommended_city": ""},
            {**GOOD, "recommended_city": 3},
            {**GOOD, "weather": None},
            {**GOOD, "events": "행사 하나"},
            {**GOOD, "events": []},
            {**GOOD, "events": ["a", "b", "c", "d"]},
            {**GOOD, "events": ["a", 1]},
            {**GOOD, "reason": ["이유"]},
            ["배열은 객체가 아님"],
        ]
        for bad in bad_cases:
            with self.subTest(bad=bad):
                with mock.patch.object(tp.requests, "post", side_effect=[llm_reply(json.dumps(bad, ensure_ascii=False)),
                                                                          llm_reply(bad if isinstance(bad, dict) else "[]")]):
                    with self.assertRaises(ValueError):
                        tp.recommend_city("2026-03-15")


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class MainExitTest(unittest.TestCase):
    # 상황: 두 번 다 읽지 못함 → 할 일: 프로그램 실행 → 기대: 종료 코드 1, 맛집 검색은 부르지 않음
    def test_main_exits_1_after_two_failures(self):
        with mock.patch.object(tp.requests, "post", side_effect=[llm_reply("x"), llm_reply("y")]), \
             mock.patch.object(tp, "search_restaurants") as search, \
             mock.patch.object(tp, "load_dotenv"):
            with self.assertRaises(SystemExit) as cm:
                tp.main(["-date", "2026-03-15"])
        self.assertEqual(cm.exception.code, 1)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
