# End-to-end tests: travel_planner.main() with Gemini and Kakao mocked (no network).
import json
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import travel_planner  # noqa: E402
from src import gemini_client, kakao_client  # noqa: E402

REC = {"recommended_city": "제주", "weather": "맑음, 15도", "events": ["유채꽃 축제"], "reason": "봄꽃이 핀다."}
DOCS = [{"place_name": "흑돼지집", "address_name": "제주시 1", "category_name": "음식점 > 한식",
         "place_url": "http://place.map.kakao.com/1", "x": "126.5", "y": "33.5"}]


class FakeModel:
    """Stands in for genai.GenerativeModel: replies are taken in order; an Exception is raised."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate_content(self, prompt):
        self.prompts.append(prompt)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return mock.Mock(text=r)


def kakao_resp(status=200, docs=DOCS):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = {"documents": docs}
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("KAKAO_API_KEY", "test-kakao")

    def _run(replies, kakao=None, date="2024-03-15"):
        model = FakeModel(replies)
        get = mock.Mock(side_effect=kakao) if isinstance(kakao, Exception) else mock.Mock(return_value=kakao or kakao_resp())
        with mock.patch.object(gemini_client.genai, "configure") as conf, \
             mock.patch.object(gemini_client.genai, "GenerativeModel", return_value=model) as gm, \
             mock.patch.object(kakao_client.requests, "get", get), \
             mock.patch.object(sys, "argv", ["travel_planner.py", "-date", date]):
            travel_planner.main()
        conf.assert_called_once_with(api_key="test-gemini")  # 시험용 가짜 값 — secret-check: allow
        gm.assert_called_once_with("gemini-1.5-flash")
        data = json.loads((tmp_path / f"results/{date}_data.json").read_text(encoding="utf-8"))
        md = (tmp_path / f"results/{date}_travel_plan.md").read_text(encoding="utf-8")
        return data, md, model, get
    return _run


def test_happy_path_writes_json_and_report(run, capsys):
    fenced = "```json\n" + json.dumps(REC, ensure_ascii=False) + "\n```"
    data, md, model, get = run([fenced, "# 제주 여행\n- 오전: 성산"])
    assert data == {"date": "2024-03-15", "recommendation": REC,
                    "restaurants": [{"name": "흑돼지집", "address": "제주시 1", "category": "음식점 > 한식",
                                     "url": "http://place.map.kakao.com/1", "x": 126.5, "y": 33.5}],
                    "errors": []}
    assert md == "# 제주 여행\n- 오전: 성산"
    assert get.call_args.kwargs["headers"] == {"Authorization": "KakaoAK test-kakao"}
    assert get.call_args.kwargs["params"]["query"] == "제주 맛집"
    assert "흑돼지집 (제주시 1)" in model.prompts[1]
    out = capsys.readouterr().out
    assert "추천 지역: 제주" in out and "맛집 1곳 검색 완료" in out and "✅ 완료!" in out


@pytest.mark.parametrize("status", [401, 403])
def test_kakao_auth_error_still_makes_report(run, status):
    data, md, model, _ = run([json.dumps(REC), "# 리포트"], kakao=kakao_resp(status))
    assert data["restaurants"] == []
    assert data["errors"] == [{"step": "place_search", "type": "AUTH_ERROR", "message": f"HTTP {status}"}]
    assert "맛집: - 데이터 없음" in model.prompts[1]
    assert md == "# 리포트"


def test_kakao_empty_and_network_error(run):
    data, _, _, _ = run([json.dumps(REC), "r"], kakao=kakao_resp(docs=[]))
    assert data["errors"][0]["type"] == "EMPTY_RESULT"
    data, _, _, _ = run([json.dumps(REC), "r"], kakao=requests.exceptions.ConnectionError("down"))
    assert data["errors"][0]["type"] == "NETWORK_ERROR" and data["restaurants"] == []


def test_llm_retry_once_then_succeeds(run):
    data, _, model, _ = run(["not json", json.dumps(REC), "r"])
    assert data["recommendation"] == REC
    assert data["errors"][0]["type"] == "JSON_PARSE_ERROR"
    assert len(model.prompts) == 3


def test_llm_fails_twice_exits(run, capsys):
    with pytest.raises(SystemExit) as e:
        run([RuntimeError("quota"), RuntimeError("quota")])
    assert e.value.code == 1
    assert "추천 생성 최종 실패" in capsys.readouterr().out


@pytest.mark.parametrize("missing,msg", [("GEMINI_API_KEY", "GEMINI_API_KEY 환경변수"),
                                         ("KAKAO_API_KEY", "KAKAO_API_KEY 환경변수")])
def test_missing_key_exits(run, monkeypatch, capsys, missing, msg):
    monkeypatch.delenv(missing)
    with pytest.raises(SystemExit) as e:
        run([])
    assert e.value.code == 1 and msg in capsys.readouterr().out


def test_bad_date_exits(run, capsys):
    with pytest.raises(SystemExit):
        run([], date="2024/03/15")
    assert "날짜 형식이 올바르지 않습니다" in capsys.readouterr().out
