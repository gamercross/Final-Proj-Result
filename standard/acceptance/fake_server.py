"""가짜 OpenAI · Kakao 서버 — 진짜 키 없이 구현을 바깥에서 돌려 보려고.

한 서버가 두 주소를 다 받는다.
- POST /v1/chat/completions  — OpenAI Chat Completions 모양으로 답한다
- GET  /v2/local/search/keyword.json — Kakao Local 키워드 검색 모양으로 답한다

1차 추천 요청과 리포트 요청은 요청 글에 추천 도시(CITY)가 들어 있는지로 가른다 —
1차 추천을 묻는 때는 아직 도시를 모르기 때문이다.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CITY = "단양"   # 1차 추천 요청에 우연히 들어 있을 일이 없는 도시

GOOD_RECO = {
    "recommended_city": CITY,
    "weather": "늦가을, 낮 12도 안팎으로 선선함",
    "events": ["단양 온달문화축제", "도담삼봉 야경"],
    "reason": "단풍이 늦게까지 남는 시기입니다. 강을 따라 걷기 좋고 붐비지 않습니다.",
}

PLACES = [
    {"place_name": f"맛집{i}호", "address_name": f"충북 단양군 단양읍 {i}길", "road_address_name": "",
     "category_name": "음식점 > 한식", "place_url": f"http://place.map.kakao.com/{1000 + i}",
     "x": f"128.36{i}", "y": f"36.98{i}", "phone": "", "id": str(1000 + i)}
    for i in range(1, 6)
]

REPORT_MD = (
    f"# {CITY} 여행\n\n단양은 강과 절벽이 어우러진 곳입니다.\n\n"
    "## 1일 일정 제안\n- 오전: 도담삼봉 산책\n- 오후: 맛집1호에서 점심 뒤 만천하스카이워크\n- 저녁: 맛집2호에서 저녁\n"
)


class Scenario:
    """시험마다 바꾸는 답. reco는 차례대로 꺼내 쓰고, 다 쓰면 마지막 것을 되풀이한다."""

    def __init__(self):
        self.reco = [json.dumps(GOOD_RECO, ensure_ascii=False)]
        self.report = REPORT_MD          # 글이면 그 글로, 정수면 그 상태 코드로 실패
        self.kakao = "ok"                # "ok" · "empty" · 정수(상태 코드)
        self.kakao_body_extra = ""       # 실패 응답 본문에 덧붙일 글(키가 섞여 오는 경우)
        self.requests = []               # (종류, 경로, 머리글, 본문)

    def calls(self, kind):
        return [r for r in self.requests if r[0] == kind]


class _Handler(BaseHTTPRequestHandler):
    server_version = "fake/1"

    def log_message(self, *a):  # 조용히
        pass

    def _send(self, code, obj):
        body = (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        sc: Scenario = self.server.scenario
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        if not urlparse(self.path).path.endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "not found"}})
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        text = json.dumps(body.get("messages", body), ensure_ascii=False)
        kind = "report" if CITY in text else "reco"
        sc.requests.append((kind, self.path, dict(self.headers), raw))
        if kind == "reco":
            i = len(sc.calls("reco")) - 1
            content = sc.reco[min(i, len(sc.reco) - 1)]
        else:
            if isinstance(sc.report, int):
                return self._send(sc.report, {"error": {"message": "server error", "type": "server_error"}})
            content = sc.report
        self._send(200, {
            "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": body.get("model", "fake"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    def do_GET(self):
        sc: Scenario = self.server.scenario
        u = urlparse(self.path)
        if u.path != "/v2/local/search/keyword.json":
            return self._send(404, {"msg": "not found"})
        sc.requests.append(("kakao", self.path, dict(self.headers), ""))
        q = parse_qs(u.query)
        if isinstance(sc.kakao, int):
            return self._send(sc.kakao, {"errorType": "Error", "message": f"fail {sc.kakao}{sc.kakao_body_extra}"})
        docs = [] if sc.kakao == "empty" else PLACES[: int((q.get("size") or ["5"])[0] or 5)]
        self._send(200, {"documents": docs, "meta": {"total_count": len(docs), "pageable_count": len(docs), "is_end": True}})


class FakeServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.scenario = Scenario()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def scenario(self) -> Scenario:
        return self.httpd.scenario

    def reset(self):
        self.httpd.scenario = Scenario()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
