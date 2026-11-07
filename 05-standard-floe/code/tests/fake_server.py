"""키 없이 뼈대를 돌려 보기 위한 가짜 OpenAI · Kakao 서버 (로컬 전용, 실제 API를 부르지 않음).

실행: python tests/fake_server.py   (http://127.0.0.1:8765)
돌려주는 값은 흐름 확인용 가짜 데이터이며 실제 장소가 아니다.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765

FAKE_RECOMMENDATION = {
    "recommended_city": "가짜도시",
    "weather": "(가짜 데이터) 날씨 요약",
    "events": ["(가짜 데이터) 행사 1"],
    "reason": "(가짜 데이터) 흐름 확인용 추천 이유입니다.",
}

FAKE_REPORT = {
    "reason_summary": "(가짜 데이터) 추천 이유 요약입니다.",
    "itinerary": {"morning": "(가짜 데이터) 오전 일정", "afternoon": "(가짜 데이터) 오후 일정",
                  "evening": "(가짜 데이터) 저녁 일정"},
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # /chat/completions — 1차 추천 또는 리포트 글
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        fake = FAKE_REPORT if "itinerary" in body else FAKE_RECOMMENDATION
        content = json.dumps(fake, ensure_ascii=False)
        self._send({"choices": [{"message": {"content": content}}]})

    def do_GET(self):  # /v2/local/search/keyword.json
        self._send({"documents": [
            {"place_name": f"(가짜) 식당 {i}", "road_address_name": "(가짜) 주소", "category_name": "음식점",
             "place_url": "", "x": "0", "y": "0"} for i in range(1, 6)
        ]})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"fake server on http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
