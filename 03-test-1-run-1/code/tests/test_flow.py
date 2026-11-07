import json
import pathlib
import re
from types import SimpleNamespace

import pytest

import app as app_module
import travel

ROOT = pathlib.Path(__file__).resolve().parent.parent

KAKAO_DOCS = {"documents": [
    {"place_name": "강릉 초당순두부", "category_name": "음식점 > 한식", "road_address_name": "강원 강릉시 초당동 1",
     "phone": "033-000-0000", "place_url": "http://place.map.kakao.com/1"},
    {"place_name": "강릉 물회집", "category_name": "음식점 > 해물", "address_name": "강원 강릉시 주문진읍 2",
     "phone": "", "place_url": "http://place.map.kakao.com/2"},
]}


class FakeAI:
    def __init__(self, content):
        self.sent = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._content = content

    def _create(self, **kw):
        self.sent.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-kakao")


@pytest.fixture
def fakes(monkeypatch, keys):
    ai = FakeAI(json.dumps({"region": "강릉", "reason": "가을 바다와 단풍이 좋아요."}, ensure_ascii=False))
    calls = []

    def fake_get(url, **kw):
        calls.append((url, kw))
        return FakeResp(KAKAO_DOCS)

    monkeypatch.setattr(travel, "OpenAI", lambda api_key: ai)
    monkeypatch.setattr(travel.requests, "get", fake_get)
    return ai, calls


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# 확인 먼저 — 날짜로 지역 추천
def test_recommend_region_returns_name():
    ai = FakeAI('{"region": "경주", "reason": "벚꽃"}')
    rec = travel.recommend_region(travel.parse_date("2026-04-05"), client=ai)
    assert rec == {"region": "경주", "reason": "벚꽃"}
    # 날짜만 나간다
    assert "2026-04-05" in ai.sent[0]["messages"][1]["content"]


def test_recommend_region_without_name_fails():
    with pytest.raises(ValueError):
        travel.recommend_region(travel.parse_date("2026-04-05"), client=FakeAI('{"reason": "x"}'))


# 맛집 찾기 — 하나 이상
def test_search_restaurants(keys):
    seen = {}

    def fake_get(url, **kw):
        seen.update(url=url, **kw)
        return FakeResp(KAKAO_DOCS)

    found = travel.search_restaurants("강릉", http_get=fake_get)
    assert len(found) >= 1
    assert found[1]["address"] == "강원 강릉시 주문진읍 2"
    assert seen["headers"]["Authorization"] == "KakaoAK test-kakao"
    assert seen["params"]["query"] == "강릉 맛집"


# 리포트 — 추천·맛집·1일 일정이 모두 들어 있다 (끝에서 끝까지)
def test_full_flow_through_server(client, fakes):
    ai, calls = fakes
    r = client.post("/api/report", json={"date": "2026-10-10", "name": "홍길동", "phone": "010"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["region"] == "강릉" and d["reason"]
    assert [x["name"] for x in d["restaurants"]] == ["강릉 초당순두부", "강릉 물회집"]
    assert "점심 — 강릉 초당순두부" in [x["plan"] for x in d["itinerary"]]
    assert "저녁 — 강릉 물회집" in [x["plan"] for x in d["itinerary"]]
    # 막을 일: 날짜 말고 다른 개인 정보는 밖으로 나가지 않는다
    sent = json.dumps(ai.sent, ensure_ascii=False) + json.dumps(calls, ensure_ascii=False, default=str)
    assert "홍길동" not in sent and "010" not in sent


def test_no_restaurants_still_reports(client, fakes, monkeypatch):
    empty = lambda url, **kw: FakeResp({"documents": []})
    monkeypatch.setattr(travel.requests, "get", empty)
    d = client.post("/api/report", json={"date": "2026-10-10"}).get_json()
    assert d["restaurants"] == [] and len(d["itinerary"]) == 4


# 날짜 입력 — 빈칸이면 안내
@pytest.mark.parametrize("body,msg", [({}, "여행 날짜를 넣어 주세요."), ({"date": "내일"}, "YYYY-MM-DD")])
def test_bad_date(client, body, msg):
    r = client.post("/api/report", json=body)
    assert r.status_code == 400 and msg in r.get_json()["error"]


def test_missing_key(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    r = client.post("/api/report", json={"date": "2026-10-10"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.get_json()["error"]


def test_external_failure_is_502(client, keys, monkeypatch):
    def boom(**kw):
        raise RuntimeError("down")
    ai = FakeAI("")
    ai.chat.completions.create = boom
    monkeypatch.setattr(travel, "OpenAI", lambda api_key: ai)
    r = client.post("/api/report", json={"date": "2026-10-10"})
    assert r.status_code == 502


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and 'type="date"' in r.get_data(as_text=True)


# 비밀값 검사 — 열쇠 글자가 코드에 남지 않았다
def test_no_secrets_in_code():
    pattern = re.compile(r"sk-[A-Za-z0-9_-]{16,}|KakaoAK [0-9a-f]{32}")
    for f in [*ROOT.glob("*.py"), *ROOT.glob("*.html"), *ROOT.glob("tests/*.py")]:
        assert not pattern.search(f.read_text(encoding="utf-8")), f
    assert ".env" in (ROOT / ".gitignore").read_text().split()
