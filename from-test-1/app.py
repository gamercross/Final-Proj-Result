"""서버가 있는 웹 — 열쇠는 서버에서만 쓴다."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

import travel

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))  # 이 폴더의 .env만 읽는다
app = Flask(__name__)


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.post("/api/report")
def report():
    # 날짜 말고 다른 값은 읽지 않는다(3단계 '막을 일').
    date_text = (request.get_json(silent=True) or {}).get("date", "")
    try:
        return jsonify(travel.make_report(date_text))
    except travel.InputError as e:
        return jsonify(error=str(e)), 400
    except travel.MissingKeyError as e:
        return jsonify(error=str(e)), 503
    except Exception as e:  # AI·지도 서비스 실패
        app.logger.warning("외부 서비스 실패: %s", type(e).__name__)
        return jsonify(error="AI나 지도 서비스를 부르다 실패했어요. 잠시 뒤 다시 해 보세요."), 502


if __name__ == "__main__":
    for name in ("OPENAI_API_KEY", "KAKAO_REST_API_KEY"):
        if not os.environ.get(name):
            print(f"[경고] {name}가 없어요 — .env에 적기 전에는 리포트를 만들 수 없어요.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
