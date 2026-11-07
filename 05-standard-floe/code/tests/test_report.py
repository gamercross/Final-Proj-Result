"""6단계 확인 — 리포트: 결과를 넣으면 한 장이 나와야 해요.

실제 API를 부르지 않고 requests.post / requests.get 을 가짜로 바꿔 확인한다.
실행: python -m unittest discover -s tests -v

상황 → 할 일 → 기대 결과
1. 추천 결과 + 맛집 목록이 모였다 → 리포트 만들기 → Markdown 한 장, 절 제목이 기준 10의 순서로 다 있다
2. 같은 결과 → HTML 만들기 → 파일 하나로 열리는 HTML 한 장, 같은 순서의 절, 바깥 글의 < > 는 이스케이프
3. 리포트 LLM이 실패한다 → 리포트 만들기 → errors 에 step "report" 가 남고, 가진 데이터로 한 장이 나온다
4. 맛집 0건 → 리포트 만들기 → '맛집 추천' 절에 "데이터 없음"
5. 프로그램 실행 → results/ 에 .json · .md · .html 세 파일, 로그에 [3/3] 과 저장 경로
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import travel_planner as tp  # noqa: E402

DATE = "2026-03-15"
REC = {"recommended_city": "가짜도시", "weather": "가짜 날씨", "events": ["가짜 행사 1", "가짜 행사 2"],
       "reason": "가짜 이유입니다."}
RESTAURANTS = [{"name": "가짜 식당", "address": "가짜 주소", "category": "음식점 > 한식",
                "url": "http://place.example/1", "x": 127.1, "y": 37.5}]
WRITTEN = {"reason_summary": "가짜 이유 요약.",
           "itinerary": {"morning": "가짜 오전 일정", "afternoon": "가짜 오후 일정", "evening": "가짜 저녁 일정"}}
TITLES = ["추천 지역", "추천 이유", "날씨 요약", "행사/축제", "맛집 추천", "1일 일정 제안", "오류 요약(errors)"]


def llm_reply(content, status=200):
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    resp = mock.Mock()
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status}", response=resp)
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def md_titles(md):
    return re.findall(r"^## (.+)$", md, flags=re.M)


def html_titles(page):
    return re.findall(r"<h2>(.+?)</h2>", page)


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class WriteReportTest(unittest.TestCase):
    def write(self, **post_kwargs):
        errors = []
        with mock.patch.object(tp.requests, "post", **post_kwargs) as post, redirect_stderr(io.StringIO()):
            written = tp.write_report(DATE, REC, RESTAURANTS, errors)
        return written, errors, post

    # 상황: 결과가 모였고 LLM이 리포트 글을 준다 → 기대: 요약과 오전 · 오후 · 저녁 일정
    def test_llm_writes_summary_and_itinerary(self):
        written, errors, post = self.write(return_value=llm_reply(WRITTEN))
        self.assertEqual(written, WRITTEN)
        self.assertEqual(errors, [])
        self.assertEqual(post.call_count, 1)

    # 막을 일: LLM에게 나가는 것은 날짜와 모인 결과(추천 · 맛집 이름/주소/분류)뿐이다
    def test_only_results_go_out(self):
        _, _, post = self.write(return_value=llm_reply(WRITTEN))
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(messages), 1)
        sent = json.loads(messages[0]["content"].split("\n", 1)[1])
        self.assertEqual(set(sent), {"date", "recommended_city", "weather", "events", "reason", "restaurants"})
        self.assertEqual(sent["restaurants"], [{"name": "가짜 식당", "address": "가짜 주소", "category": "음식점 > 한식"}])

    # 상황: 리포트 LLM이 실패한다(읽지 못함 · 401 · 429 · 네트워크) → 기대: None + errors 에 step "report"
    def test_failures_leave_report_error(self):
        cases = [
            ({"return_value": llm_reply("JSON 아님")}, "PARSE_ERROR"),
            ({"return_value": llm_reply({"reason_summary": "요약만"})}, "PARSE_ERROR"),
            ({"return_value": llm_reply({**WRITTEN, "itinerary": {"morning": "오전만"}})}, "PARSE_ERROR"),
            ({"return_value": llm_reply("", status=401)}, "AUTH_ERROR"),
            ({"return_value": llm_reply("", status=429)}, "QUOTA_ERROR"),
            ({"side_effect": requests.ConnectionError("x")}, "NETWORK_ERROR"),
        ]
        for kwargs, kind in cases:
            with self.subTest(kind=kind, kwargs=kwargs):
                written, errors, post = self.write(**kwargs)
                self.assertIsNone(written)
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0]["step"], "report")
                self.assertEqual(errors[0]["type"], kind)
                self.assertEqual(post.call_count, 1)  # 다시 요청하지 않는다

    # 키 값은 errors 에 들어가지 않는다
    def test_key_not_in_errors(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET-KEY-123"}):
            _, errors, _ = self.write(side_effect=requests.ConnectionError("SECRET-KEY-123"))
        self.assertNotIn("SECRET-KEY-123", json.dumps(errors))


class BuildReportTest(unittest.TestCase):
    # 상황: 결과 + LLM 글 → 할 일: Markdown 만들기 → 기대: 한 장, 기준 10 순서의 절, 모인 결과가 담김
    def test_markdown_one_page_in_order(self):
        md = tp.build_report(DATE, REC, RESTAURANTS, [], WRITTEN)
        self.assertTrue(md.startswith(f"# {DATE} 국내 여행 추천 리포트\n"))
        self.assertEqual(md.count("\n# "), 0)  # 맨 위 제목은 하나
        self.assertEqual(md_titles(md), TITLES)
        for text in ["가짜도시", "가짜 이유 요약.", "가짜 날씨", "- 가짜 행사 1", "가짜 식당",
                     "- 오전: 가짜 오전 일정", "- 오후: 가짜 오후 일정", "- 저녁: 가짜 저녁 일정"]:
            self.assertIn(text, md)
        self.assertIn("## 오류 요약(errors)\n- 없음", md)

    # 상황: 리포트 LLM 실패(written 없음) → 기대: 가진 데이터로 한 장, 이유는 1차 추천 그대로, 일정은 데이터 없음
    def test_markdown_without_llm_uses_data(self):
        errors = [{"step": "report", "type": "NETWORK_ERROR", "message": "ConnectionError"}]
        md = tp.build_report(DATE, REC, RESTAURANTS, errors, None)
        self.assertEqual(md_titles(md), TITLES)
        self.assertIn("## 추천 이유\n가짜 이유입니다.", md)
        self.assertIn("- 오전: 데이터 없음", md)
        self.assertIn("- report · NETWORK_ERROR · ConnectionError", md)

    # 상황: 맛집 0건 → 기대: '맛집 추천' 절에 데이터 없음
    def test_no_restaurants(self):
        md = tp.build_report(DATE, REC, [], [], WRITTEN)
        self.assertIn("## 맛집 추천\n- 데이터 없음", md)

    # 상황: 같은 결과 → 할 일: HTML 만들기 → 기대: 파일 하나, 같은 순서의 절, 바깥을 부르지 않음
    def test_html_one_file_in_order(self):
        page = tp.build_html(DATE, REC, RESTAURANTS, [], WRITTEN)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertIn(f"<h1>{DATE} 국내 여행 추천 리포트</h1>", page)
        self.assertEqual(html_titles(page), TITLES)
        self.assertIn("<li>오전: 가짜 오전 일정</li>", page)
        for outside in ["<script", "<link", "@import", "src=", "href="]:
            self.assertNotIn(outside, page)

    # 기준 11: 바깥에서 온 글(LLM · 지도)의 < > 는 이스케이프한다
    def test_html_escapes_outside_text(self):
        rec = {**REC, "recommended_city": "<script>alert(1)</script>"}
        rests = [{**RESTAURANTS[0], "name": "<b>식당</b>"}]
        written = {**WRITTEN, "itinerary": {**WRITTEN["itinerary"], "evening": "<img src=x>"}}
        page = tp.build_html(DATE, rec, rests, [], written)
        self.assertNotIn("<script>", page)
        self.assertNotIn("<b>", page)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("&lt;b&gt;식당&lt;/b&gt;", page)

    def test_html_no_restaurants(self):
        page = tp.build_html(DATE, REC, [], [], None)
        self.assertIn("<h2>맛집 추천</h2>\n<ul>\n<li>데이터 없음</li>", page)


@mock.patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "KAKAO_REST_API_KEY": "dummy"})
class MainReportTest(unittest.TestCase):
    def run_main(self, report_reply):
        map_resp = mock.Mock()
        map_resp.raise_for_status.return_value = None
        map_resp.json.return_value = {"documents": [{"place_name": "가짜 식당", "road_address_name": "가짜 주소",
                                                     "category_name": "음식점", "place_url": "", "x": "1", "y": "2"}]}
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(tp, "RESULTS_DIR", Path(tmp)), mock.patch.object(tp, "load_dotenv"), \
             mock.patch.object(tp.requests, "post", side_effect=[llm_reply(REC), report_reply]), \
             mock.patch.object(tp.requests, "get", return_value=map_resp), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            tp.main(["-date", DATE])
            files = sorted(p.name for p in Path(tmp).iterdir())
            data = json.loads((Path(tmp) / f"{DATE}_data.json").read_text(encoding="utf-8"))
            md = (Path(tmp) / f"{DATE}_travel_plan.md").read_text(encoding="utf-8")
            page = (Path(tmp) / f"{DATE}_travel_plan.html").read_text(encoding="utf-8")
        return files, data, md, page, out.getvalue()

    # 상황: 날짜 → 추천 → 맛집 → 할 일: 프로그램 실행 → 기대: 세 파일, 로그 [3/3] 과 저장 경로
    def test_results_make_one_report(self):
        files, data, md, page, out = self.run_main(llm_reply(WRITTEN))
        self.assertEqual(files, [f"{DATE}_data.json", f"{DATE}_travel_plan.html", f"{DATE}_travel_plan.md"])
        self.assertEqual(set(data), {"date", "recommendation", "restaurants", "errors"})
        self.assertEqual(data["errors"], [])
        self.assertEqual(md_titles(md), TITLES)
        self.assertEqual(html_titles(page), TITLES)
        self.assertIn("- 오전: 가짜 오전 일정", md)
        self.assertIn("[3/3]", out)
        self.assertIn(f"{DATE}_travel_plan.md", out)
        self.assertIn(f"{DATE}_travel_plan.html", out)

    # 상황: 리포트 LLM 실패 → 기대: 멈추지 않고 세 파일, errors 에 step "report"(json · md · html 모두)
    def test_report_failure_still_makes_report(self):
        files, data, md, page, _ = self.run_main(llm_reply("", status=500))
        self.assertEqual(len(files), 3)
        self.assertEqual([e["step"] for e in data["errors"]], ["report"])
        self.assertIn("- report · NETWORK_ERROR · HTTP 500", md)
        self.assertIn("report · NETWORK_ERROR · HTTP 500", page)
        self.assertIn("## 추천 이유\n가짜 이유입니다.", md)


if __name__ == "__main__":
    unittest.main()
