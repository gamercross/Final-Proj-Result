"""수용 시험 — 기준 v1(../STANDARD.md)의 줄마다. 시험 이름 앞의 번호가 기준의 번호다.

구현 안을 보지 않는다. 바깥에서 돌리고 화면 글 · 끝 코드 · results/ 파일 · 가짜 서버가 받은 요청만 본다.
"""
from __future__ import annotations

import html as htmllib
import json
import re

import pytest

from conftest import DATE, KAKAO_KEY, OPENAI_KEY
from fake_server import CITY, GOOD_RECO, PLACES

TITLE = f"{DATE} 국내 여행 추천 리포트"
SECTIONS = ["추천 지역", "추천 이유", "날씨 요약", "행사/축제", "맛집 추천", "1일 일정 제안", "오류 요약(errors)"]
NAMES = [p["place_name"] for p in PLACES]


# ── 읽는 도우미 ──
def files(cwd):
    r = cwd / "results"
    return r / f"{DATE}_data.json", r / f"{DATE}_travel_plan.md", r / f"{DATE}_travel_plan.html"


def data_of(cwd):
    return json.loads(files(cwd)[0].read_text(encoding="utf-8"))


def md_heads(text):
    return [(i, re.sub(r"^#+\s*", "", l).strip()) for i, l in enumerate(text.splitlines()) if re.match(r"^#{1,6}\s", l)]


def html_heads(text):
    return [(m.start(), htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip())
            for m in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", text, re.S | re.I)]


def norm(s):
    return re.sub(r"\s+", "", s)


def order_ok(heads):
    """맨 위 제목 다음에 일곱 절이 이 순서로 나오는가 — 사이에 다른 제목이 있어도 된다."""
    if not heads or TITLE.replace(" ", "") not in norm(heads[0][1]):
        return f"맨 위 제목이 '{TITLE}'가 아님: {heads[:1]}"
    pos = []
    for s in SECTIONS:
        hit = [p for p, h in heads[1:] if norm(s) in norm(h)]
        if not hit:
            return f"절이 없음: {s}"
        pos.append(hit[0])
    return None if pos == sorted(pos) else f"절 순서가 다름: {[h for _, h in heads]}"


def md_section(text, name):
    lines = text.splitlines()
    heads = md_heads(text)
    start = next((i for i, h in heads if norm(name) in norm(h)), None)
    if start is None:
        return ""
    later = [i for i, h in heads if i > start and any(norm(s) in norm(h) for s in SECTIONS)]
    end = later[0] if later else len(lines)
    return "\n".join(lines[start + 1:end])


def assert_place_error(cwd, typ):
    errs = data_of(cwd)["errors"]
    assert any(e.get("step") == "place_search" and e.get("type") == typ for e in errs), errs
    assert data_of(cwd)["restaurants"] == []
    md = files(cwd)[1].read_text(encoding="utf-8")
    assert "데이터 없음" in md_section(md, "맛집 추천")


# ── 1 · 12 · 9: 정상 흐름 ──
def test_01_runs_and_saves_three_files(run):
    code, out, cwd = run()
    assert code == 0, out
    for f in files(cwd):
        assert f.is_file(), f"없음: {f.name}\n{out}"


def test_12_progress_log(run):
    code, out, _ = run()
    for t in ("[1/3]", "[2/3]", "[3/3]", "results/"):
        assert t in out, f"화면에 '{t}'가 없음\n{out}"


def test_09_json_shape(run):
    code, out, cwd = run()
    d = data_of(cwd)
    assert set(("date", "recommendation", "restaurants", "errors")) <= set(d), d.keys()
    assert d["date"] == DATE
    r = d["recommendation"]
    assert r["recommended_city"] == CITY
    assert isinstance(r["weather"], str) and isinstance(r["reason"], str)
    assert isinstance(r["events"], list) and 1 <= len(r["events"]) <= 3
    # 리포트 요청의 응답 모양은 기준이 정하지 않았다 — 가짜 서버는 늘 Markdown으로 답하므로, 다른 모양을 바라는 구현이
    # 남긴 report 단계 오류는 세지 않는다(2026-11-07 첫 실행 뒤 고침 — README '시험을 고친 기록')
    assert [e for e in d["errors"] if e.get("step") != "report"] == [], d["errors"]


def test_07_restaurants_shape(run):
    code, out, cwd = run()
    rs = data_of(cwd)["restaurants"]
    assert len(rs) == 5
    for it in rs:
        for k in ("name", "address", "category", "url", "x", "y"):
            assert k in it, it
        assert isinstance(it["x"], (int, float)) and isinstance(it["y"], (int, float)), it
    assert [it["name"] for it in rs] == NAMES


# ── 2 · 3 · 6: 서비스를 기준대로 부르는가 ──
def test_02_03_calls_openai_then_kakao_with_city(run, server):
    code, out, _ = run()
    sc = server.scenario
    reco, kakao = sc.calls("reco"), sc.calls("kakao")
    assert len(reco) == 1, f"1차 추천 요청 {len(reco)}번"
    assert reco[0][2].get("Authorization") == f"Bearer {OPENAI_KEY}"
    assert len(kakao) == 1
    assert kakao[0][2].get("Authorization") == f"KakaoAK {KAKAO_KEY}"
    assert CITY in __import__("urllib.parse").parse.unquote(kakao[0][1]), kakao[0][1]
    assert sc.calls("report"), "리포트를 LLM으로 만들지 않음"


# ── 10: Markdown 절 ──
def test_10_markdown_sections(run):
    code, out, cwd = run()
    md = files(cwd)[1].read_text(encoding="utf-8")
    assert order_ok(md_heads(md)) is None, order_ok(md_heads(md))
    assert CITY in md_section(md, "추천 지역")
    assert md_section(md, "추천 이유").strip() and md_section(md, "날씨 요약").strip()
    assert any(e in md_section(md, "행사/축제") for e in GOOD_RECO["events"])
    shop = md_section(md, "맛집 추천")
    assert all(n in shop for n in NAMES), shop
    day = md_section(md, "1일 일정 제안")
    assert all(w in day for w in ("오전", "오후", "저녁")), day


# ── 10 · 11: HTML ──
def test_10_html_sections(run):
    code, out, cwd = run()
    h = files(cwd)[2].read_text(encoding="utf-8")
    assert order_ok(html_heads(h)) is None, order_ok(html_heads(h))
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", h))
    assert all(n in text for n in NAMES)


def test_11_html_is_self_contained(run):
    code, out, cwd = run()
    h = files(cwd)[2].read_text(encoding="utf-8")
    bad = re.findall(r"<script[^>]+src\s*=|<link[^>]+href\s*=\s*[\"']https?:|@import|src\s*=\s*[\"']https?:", h, re.I)
    assert not bad, bad


def test_11_html_escapes_outside_text(run, server):
    evil = dict(GOOD_RECO, reason="좋아요 <script>alert('x')</script> <b>굵게</b>")
    server.scenario.reco = [json.dumps(evil, ensure_ascii=False)]
    code, out, cwd = run()
    assert code == 0, out
    h = files(cwd)[2].read_text(encoding="utf-8")
    assert "<script>alert(" not in h and "<b>굵게</b>" not in h


# ── 5 · 4: 입력 · 키 ──
def test_05_bad_date_shows_usage(run, server):
    code, out, cwd = run(date="2026-13-40")
    assert code == 2, (code, out)
    assert "usage" in out.lower()
    assert not server.scenario.requests


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "KAKAO_REST_API_KEY"])
def test_04_missing_key_stops_before_calls(run, server, missing):
    code, out, cwd = run(env_drop=(missing,))
    assert code == 1, (code, out)
    assert missing in out
    assert not server.scenario.requests, "키가 없는데 바깥을 불렀음"


# ── 6: 1차 추천 JSON 재시도 ──
@pytest.mark.parametrize("bad", ["여기 추천입니다! 제주가 좋아요", json.dumps({"recommended_city": CITY}, ensure_ascii=False)],
                         ids=["not-json", "missing-keys"])
def test_06_retry_once_then_ok(run, server, bad):
    server.scenario.reco = [bad, json.dumps(GOOD_RECO, ensure_ascii=False)]
    code, out, cwd = run()
    assert code == 0, out
    assert len(server.scenario.calls("reco")) == 2


def test_06_two_failures_stop(run, server):
    server.scenario.reco = ["아니요", "그래도 아니요"]
    code, out, cwd = run()
    assert code == 1, (code, out)
    assert len(server.scenario.calls("reco")) == 2, "재시도는 딱 한 번"
    assert not server.scenario.calls("kakao")


# ── 7: 지도 실패에도 계속 ──
def test_07_empty_result(run, server):
    server.scenario.kakao = "empty"
    code, out, cwd = run()
    assert code == 0, out
    assert_place_error(cwd, "EMPTY_RESULT")


@pytest.mark.parametrize("status", [401, 403])
def test_07_auth_error(run, server, status):
    server.scenario.kakao = status
    code, out, cwd = run()
    assert code == 0, out
    assert_place_error(cwd, "AUTH_ERROR")


def test_07_quota_error(run, server):
    server.scenario.kakao = 429
    code, out, cwd = run()
    assert code == 0, out
    assert_place_error(cwd, "QUOTA_ERROR")


def test_07_network_error(run, server):
    code, out, cwd = run(env_set={"KAKAO_BASE_URL": "http://127.0.0.1:9"})
    assert code == 0, out
    assert_place_error(cwd, "NETWORK_ERROR")


# ── 8: 리포트 LLM 실패에도 리포트 ──
def test_08_report_llm_failure_still_writes_report(run, server):
    server.scenario.report = 500
    code, out, cwd = run()
    assert code == 0, out
    assert any(e.get("step") == "report" for e in data_of(cwd)["errors"])
    md = files(cwd)[1].read_text(encoding="utf-8")
    assert order_ok(md_heads(md)) is None, order_ok(md_heads(md))


def test_10_errors_section_lists_errors(run, server):
    server.scenario.kakao = 401
    code, out, cwd = run()
    md = files(cwd)[1].read_text(encoding="utf-8")
    assert "AUTH_ERROR" in md_section(md, "오류 요약(errors)")


# ── 13: 키를 남기지 않는다 ──
def test_13_keys_never_leak(run, server):
    server.scenario.kakao = 401
    server.scenario.kakao_body_extra = f" (key={KAKAO_KEY})"
    code, out, cwd = run()
    blobs = [out] + [p.read_text(encoding="utf-8", errors="replace") for p in (cwd / "results").glob("*") if p.is_file()]
    for b in blobs:
        assert OPENAI_KEY not in b and KAKAO_KEY not in b


# ── 14: README ──
def test_14_readme(impl):
    p = impl / "README.md"
    assert p.is_file()
    t = p.read_text(encoding="utf-8")
    for need in ("OPENAI_API_KEY", "KAKAO_REST_API_KEY", "-date", "results"):
        assert need in t, f"README에 '{need}'가 없음"
    assert any(w in t for w in ("유출", "노출", "커밋하지")), "키 유출 주의가 없음"
