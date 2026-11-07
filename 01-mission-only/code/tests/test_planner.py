"""API 키 없이 실행 가능한 테스트. requests.request를 가짜 응답으로 바꿔 오류 처리 정책을 검증한다.

실행:  python -m unittest -v
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

import requests

import travel_planner
from planner import errors as E
from planner.llm import RecommendationError, extract_json, recommend
from planner.places import KakaoPlaces, search_all
from planner.report import NO_DATA, build_report_payload, generate_report, missing_headings

FAKE_OPENAI = "sk-test-FAKEKEY1234567890"
FAKE_KAKAO = "kakaoFAKEKEY0987654321"

GOOD_REC = {
    "recommended_city": "제주",
    "weather": "온화함",
    "events": ["유채꽃 축제"],
    "reason": "봄꽃이 좋습니다. 비수기라 저렴합니다.",
}


def fake_response(status: int, body) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode()
    return resp


def openai_reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.name = "scripted"

    def complete(self, system, user, *, json_mode=False):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def quiet(fn, *a, **kw):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


class ExtractJsonTest(unittest.TestCase):
    def test_code_fence_and_chatter(self):
        text = '물론입니다!\n```json\n{"a": 1}\n```\n도움이 되길 바랍니다.'
        self.assertEqual(extract_json(text), {"a": 1})

    def test_embedded_object(self):
        self.assertEqual(extract_json('결과: {"a": [1, 2]} 끝'), {"a": [1, 2]})

    def test_garbage_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            extract_json("JSON 없음")


class RecommendRetryTest(unittest.TestCase):
    def test_retry_once_then_success(self):
        llm = ScriptedLLM(["이건 JSON이 아님", json.dumps(GOOD_REC, ensure_ascii=False)])
        errs = E.ErrorLog()
        rec = quiet(recommend, llm, date(2026, 3, 15), 1, errs)
        self.assertEqual(rec["recommended_city"], "제주")
        self.assertEqual(llm.calls, 2)
        self.assertEqual(errs.to_list()[0]["type"], E.PARSE_ERROR)

    def test_gives_up_after_one_retry(self):
        llm = ScriptedLLM(["bad", '{"recommended_city": "제주"}', "never used"])
        errs = E.ErrorLog()
        with self.assertRaises(RecommendationError):
            quiet(recommend, llm, date(2026, 3, 15), 1, errs)
        self.assertEqual(llm.calls, 2)  # 무한 재시도 금지: 정확히 2회
        self.assertEqual([e["type"] for e in errs.to_list()], [E.PARSE_ERROR, E.VALIDATION_ERROR])

    def test_api_error_not_retried(self):
        llm = ScriptedLLM([E.APIError(E.QUOTA_ERROR, "HTTP 429")])
        with self.assertRaises(RecommendationError):
            quiet(recommend, llm, date(2026, 3, 15), 1, E.ErrorLog())
        self.assertEqual(llm.calls, 1)

    def test_events_string_is_normalized(self):
        llm = ScriptedLLM([json.dumps({**GOOD_REC, "events": "축제 하나"})])
        rec = quiet(recommend, llm, date(2026, 3, 15), 1, E.ErrorLog())
        self.assertEqual(rec["events"], ["축제 하나"])


class PlaceSearchTest(unittest.TestCase):
    def run_search(self, side_effect):
        errs = E.ErrorLog()
        with mock.patch("planner.errors.requests.request", side_effect=side_effect) as req:
            out = quiet(search_all, KakaoPlaces(FAKE_KAKAO), ["제주"], 5, errs)
        return out[0], errs.to_list(), req

    def test_auth_error_continues(self):
        entry, errs, _ = self.run_search([fake_response(401, {"msg": "invalid key"})])
        self.assertEqual(entry["status"], "error")
        self.assertEqual(entry["items"], [])
        self.assertEqual(errs[0]["type"], E.AUTH_ERROR)
        self.assertIn("HTTP 401", errs[0]["message"])

    def test_empty_result(self):
        entry, errs, _ = self.run_search([fake_response(200, {"documents": [], "meta": {}})])
        self.assertEqual(entry["status"], "empty")
        self.assertEqual(errs[0]["type"], E.EMPTY_RESULT)

    def test_network_error(self):
        entry, errs, _ = self.run_search(requests.ConnectionError("down"))
        self.assertEqual(errs[0]["type"], E.NETWORK_ERROR)

    def test_quota_error(self):
        _, errs, _ = self.run_search([fake_response(429, {"message": "limit"})])
        self.assertEqual(errs[0]["type"], E.QUOTA_ERROR)

    def test_success_and_request_shape(self):
        doc = {"place_name": "가게", "road_address_name": "제주시 1", "category_name": "음식점 > 한식",
               "place_url": "http://place.map.kakao.com/1", "x": "126.5", "y": "33.4"}
        entry, errs, req = self.run_search([fake_response(200, {"documents": [doc]})])
        self.assertEqual(errs, [])
        item = entry["items"][0]
        self.assertEqual((item["name"], item["category"], item["lat"], item["lng"]), ("가게", "한식", 33.4, 126.5))
        method, url = req.call_args.args
        self.assertEqual(method, "GET")
        self.assertEqual(req.call_args.kwargs["headers"]["Authorization"], f"KakaoAK {FAKE_KAKAO}")
        self.assertEqual(req.call_args.kwargs["params"]["category_group_code"], "FD6")


class ReportTest(unittest.TestCase):
    rec = {**GOOD_REC, "recommended_cities": [{"city": "제주", "weather": "온화함",
                                                "events": ["유채꽃 축제"], "reason": "좋음"}]}

    def test_no_restaurants_marked_no_data(self):
        payload = build_report_payload(self.rec, [{"city": "제주", "status": "empty", "items": []}])
        llm = ScriptedLLM(["# 제목\n## 추천 지역\n제주"])  # 필수 섹션 누락 -> 템플릿 대체
        errs = E.ErrorLog()
        md, source = quiet(generate_report, llm, date(2026, 3, 15), payload, errs)
        self.assertEqual(source, "template")
        self.assertEqual(missing_headings(md), [])
        self.assertIn(f"- {NO_DATA} (장소 검색 결과 0건)", md)
        self.assertEqual(errs.to_list()[0]["type"], E.VALIDATION_ERROR)


class EndToEndTest(unittest.TestCase):
    """실제 OpenAI/Kakao 클라이언트 코드를 가짜 HTTP 응답으로 끝까지 실행."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": FAKE_OPENAI,
                                                "KAKAO_REST_API_KEY": FAKE_KAKAO}, clear=False)
        self.env.start()
        self.dotenv = mock.patch("planner.config.load_dotenv")  # 로컬 .env 영향 제거
        self.dotenv.start()

    def tearDown(self):
        self.env.stop()
        self.dotenv.stop()
        self.tmp.cleanup()

    def fake_http(self, kakao_status=401):
        def handler(method, url, **kw):
            if "openai.com" in url:
                assert method == "POST"
                assert kw["headers"]["Authorization"] == f"Bearer {FAKE_OPENAI}"
                if "response_format" in kw["json"]:
                    return fake_response(200, openai_reply(json.dumps(GOOD_REC, ensure_ascii=False)))
                md = "\n".join(["# 리포트", "## 추천 지역", "## 추천 이유", "## 날씨 요약", "## 행사/축제",
                                "## 맛집 추천", "- 데이터 없음", "## 1일 일정 제안", "## 오류 요약(errors)", "LLM이 쓴 가짜"])
                return fake_response(200, openai_reply(md))
            if "kakao.com" in url:
                return fake_response(kakao_status, {"errorType": "AccessDenied",
                                                    "message": f"bad key {FAKE_KAKAO}"})
            raise AssertionError(url)
        return handler

    def run_main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = travel_planner.main(["--date", "2026-03-15", "--out-dir", str(self.out), *extra])
        return code, out.getvalue() + err.getvalue()

    def test_kakao_auth_failure_still_makes_report(self):
        with mock.patch("planner.errors.requests.request", side_effect=self.fake_http(401)):
            code, log = self.run_main()
        self.assertEqual(code, 0)
        raw = json.loads((self.out / "2026-03-15_raw.json").read_text())
        self.assertEqual(raw["recommendation"]["recommended_city"], "제주")
        self.assertEqual(raw["restaurants"][0]["items"], [])
        self.assertEqual(raw["errors"][0]["type"], "AUTH_ERROR")
        md = (self.out / "2026-03-15_travel_plan.md").read_text()
        self.assertIn("| place_search | AUTH_ERROR |", md)
        self.assertNotIn("LLM이 쓴 가짜", md)  # LLM이 쓴 오류 섹션은 프로그램 것으로 교체
        self.assertTrue((self.out / "2026-03-15_travel_plan.html").exists())
        # 키가 어디에도 노출되지 않아야 함
        for f in self.out.iterdir():
            text = f.read_text()
            self.assertNotIn(FAKE_KAKAO, text, f.name)
            self.assertNotIn(FAKE_OPENAI, text, f.name)
        self.assertNotIn(FAKE_KAKAO, log)

    def test_cache_skips_api_on_rerun(self):
        with mock.patch("planner.errors.requests.request", side_effect=self.fake_http(200)) as req:
            # 카카오 200 + documents 없음 -> PARSE_ERROR 이므로 캐시 대상 아님. 빈 결과로 바꿔서 테스트
            req.side_effect = lambda m, u, **kw: (fake_response(200, {"documents": []})
                                                  if "kakao" in u else self.fake_http()(m, u, **kw))
            self.assertEqual(self.run_main()[0], 0)
            calls = req.call_count
            code, log = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("캐시 사용", log)
        self.assertEqual(req.call_count, calls)  # 두 번째 실행에서 API 호출 없음

    def test_missing_key_exits(self):
        with mock.patch.dict(os.environ, {"KAKAO_REST_API_KEY": ""}):
            code, log = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("KAKAO_REST_API_KEY", log)
        self.assertFalse(any(self.out.iterdir()))

    def test_bad_date_prints_usage(self):
        with self.assertRaises(SystemExit) as cm:
            quiet(travel_planner.main, ["-date", "2026/03/15"])
        self.assertEqual(cm.exception.code, 2)


class GeminiClientTest(unittest.TestCase):
    def test_request_and_parse(self):
        from planner.llm import GeminiClient

        body = {"candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": " 1}"}]}}]}
        with mock.patch("planner.errors.requests.request", return_value=fake_response(200, body)) as req:
            text = GeminiClient("AIzaFAKEFAKEFAKEFAKEFAKE00", "gemini-2.5-flash").complete("s", "u", json_mode=True)
        self.assertEqual(json.loads(text), {"a": 1})
        method, url = req.call_args.args
        self.assertEqual(method, "POST")
        self.assertNotIn("key=", url)  # 키는 URL이 아니라 헤더로
        self.assertEqual(req.call_args.kwargs["headers"]["x-goog-api-key"], "AIzaFAKEFAKEFAKEFAKEFAKE00")
        self.assertEqual(req.call_args.kwargs["json"]["generationConfig"]["responseMimeType"], "application/json")


class RedactTest(unittest.TestCase):
    def test_patterns(self):
        self.assertEqual(E.redact("Incorrect API key provided: sk-abc123456789"), "Incorrect API key provided: ***")


if __name__ == "__main__":
    unittest.main()
