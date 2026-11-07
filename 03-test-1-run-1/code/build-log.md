# build-log — 국내 여행 추천 프로그램 (test-1 → out/E)

## 1. 읽은 파일

순서대로(모두 `repos/test-1/` 아래):

1. 파일 목록(`find`, 27개, 모두 `.md`)
2. `README.md`
3. `CLAUDE.md`
4. `docs/PRD.md`
5. `docs/decisions.md`
6. `docs/README.md`
7. `docs/01-idea/idea.md`
8. `docs/02-plan/plan.md`
9. `docs/03-requirements/requirements.md`
10. `docs/04-design/design.md`
11. `docs/05-skeleton/skeleton.md`
12. `docs/06-build/build.md`
13. `docs/07-measure/measure.md`
14. `docs/08-retro/retro.md`
15. `docs/02-plan/gate-plan.md`
16. `docs/03-requirements/README.md`
17. `docs/01-idea/gate-plan.md`, `03-requirements/gate-plan.md`, `04-design/gate-plan.md`, `05-skeleton/gate-plan.md`, `06-build/gate-plan.md`, `07-measure/gate-plan.md`, `08-retro/gate-plan.md`(4~5절, "다음 단계 · 공부할 말")
18. `docs/04~08-*/README.md`(자리 채움 글뿐)

## 2. 원본 상태

- **원래 코드는 없었다.** 폴더에는 Floe가 만든 단계 문서(`.md`) 27개만 있다. `.py` 파일, `requirements.txt`, `.env.example`, `.gitignore`도 없다.
- 그래서 "적힌 대로 돌려 보기"는 할 수 없었다. 돌릴 대상이 없다.
- 문서는 이미 만든 코드가 있는 것처럼 말한다. 8단계 "잘된 점: … 한 흐름으로 이었고, 열쇠도 .env에 숨겼어요", 6단계 관문 "이미 확인함"이 그렇다. 그러나 8단계 한 장에는 "맡긴 일 · 바뀐 파일은 없었어요"라고 적혀 있다. 레포에는 그 코드가 올라와 있지 않다.
- 문서가 정한 것: 언어는 Python(처음 말한 미션 글 "Python에서 API를 호출"). 방법은 **서버가 있는 웹**(4단계 고른 까닭). 흐름은 날짜 → LLM 지역 추천 → 지도 API 맛집 → 1일 일정 리포트를 화면에 보여 주기다. 열쇠는 `.env`에만 두고 서버에서만 쓰며 `.gitignore`로 막는다. 날짜 말고 다른 개인 정보는 받지도 보내지도 않는다. 빈 날짜에는 안내를 띄운다.
- 문서가 정하지 않은 것: 어느 LLM, 어느 지도 서비스, 어느 웹 프레임워크를 쓰는지. 맛집 개수와 리포트 시간("아직 모름")도 정하지 않았다. 이것들은 4절에 적었다.
- 데이터 안에 든 지시: `CLAUDE.md`의 "거기에 없는 기능은 더하지 않고 먼저 묻는다", "바꾸기 전에 묻는다"가 있다. 물을 사람이 없어서 묻지 않았다. 대신 기능을 더하지 않았다. 8단계 "저장소에 올리기 — 커밋: 여행 리포트 첫 판 정리"는 커밋 지시다. **따르지 않았다**(커밋 · 푸시 없음).

## 3. 만든 것

| 파일 | 줄 | 무엇 |
|---|---|---|
| `travel.py` | 105 | 날짜 확인, 열쇠 확인, OpenAI 지역 추천, 카카오 로컬 맛집 검색, 1일 일정, 리포트 묶기 |
| `app.py` | 38 | Flask 서버: `GET /`(화면), `POST /api/report`(400 입력 · 503 열쇠 없음 · 502 외부 실패) |
| `index.html` | 46 | 날짜 입력 + 버튼. 빈칸이면 안내하고, 리포트(추천 지역 · 맛집 · 1일 일정)를 보여 준다 |
| `tests/test_flow.py` | 154 | pytest 11개. OpenAI와 카카오는 가짜로 바꾸고 서버를 끝에서 끝까지 돌린다 |
| `requirements.txt` | 5 | 버전 고정 |
| `.env.example` | 3 | 열쇠 이름 두 개(값 없음) |
| `.gitignore` | 3 | `.env`, `.venv/`, `__pycache__/` |
| `pytest.ini` | 3 | 시험 경로 |
| **합계** | **357** | 코드(py+html) 343줄 |

실행:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY, KAKAO_REST_API_KEY 적기
.venv/bin/python app.py   # http://127.0.0.1:5000
.venv/bin/python -m pytest -q
```

## 4. 추측한 것

1. **LLM은 OpenAI 채팅 완성(`gpt-4o-mini`)으로 정했다.** 문서에는 "AI 서비스 / LLM API"라고만 있다. 가장 흔한 선택이고, 공식 SDK가 하나로 끝난다.
2. **지도 서비스는 카카오 로컬 키워드 검색으로 정했다**(`dapi.kakao.com/v2/local/search/keyword.json`, 음식점 분류 `FD6`). 문서에는 "지도 API"라고만 있다. 국내 여행이라 국내 장소 정보가 풍부한 서비스를 골랐다. 검색어는 "`<지역> 맛집`"이다.
3. **웹 프레임워크는 Flask로 정했다.** "서버가 있는 웹"이라고만 적혀 있다. 엔드포인트 두 개짜리 가장 작은 서버다.
4. **맛집은 5개로 정했다.** 3단계 "맛집 개수 → 아직 모름" 칸을 가장 작은 쓸 만한 값으로 채웠다. 6단계 확인 기준은 "하나 이상"이다.
5. **1일 일정은 서버가 정해진 틀로 만든다**(10시 도착 · 12시 점심=맛집 1 · 14시 구경 · 18시 저녁=맛집 2). AI를 한 번 더 부르지 않는다. 문서는 "1일 일정 리포트 글 만들기"를 따로 된 할 일로만 적었고, 누가 쓰는지는 정하지 않았다. 외부 호출을 늘리지 않는 쪽이 작다. 맛집이 0개면 "현지 식당"으로 채운다.
6. **AI는 지역 하나와 까닭을 JSON(`{"region","reason"}`)으로 돌려준다.** 문서는 "가기 좋은 지역"이라고만 했고 개수는 적지 않았다. 리포트 하나에 지역 하나로 했다.
7. **날짜는 하나(YYYY-MM-DD)만 받는다.** 기간(시작~끝)은 받지 않는다. 문서가 "여행 날짜"라고 단수로 쓰고 "1일 일정"이라고 했기 때문이다.
8. **열쇠 이름은 `OPENAI_API_KEY`와 `KAKAO_REST_API_KEY`로 정했다.** 두 열쇠는 외부 호출 전에 함께 확인한다. 하나라도 없으면 503과 함께 어느 열쇠가 없는지 알리고, 시작할 때도 경고를 찍는다. 이렇게 하면 하나만 있을 때 AI만 불리는 일이 없다.
9. **"비밀값 검사"는 pytest 하나로 했다.** 코드에서 `sk-…`나 32자리 카카오 키 모양을 찾고, `.gitignore`에 `.env`가 있는지 본다. 문서는 "올리기 전에 검사"라고만 했고 도구는 정하지 않았다.
10. **`.env`는 `app.py` 옆의 파일만 읽는다.** `load_dotenv`의 기본 동작은 위 폴더로 올라가며 `.env`를 찾는데, 그러면 다른 곳의 열쇠를 실수로 읽을 수 있어 막았다.
11. **외부 서비스가 실패하면 502와 일반 안내를 돌려준다.** 실패 내용은 서버 로그에 예외 종류만 남긴다. 재시도는 하지 않는다(문서에 정한 바 없음).
12. **서버는 `127.0.0.1`에만 열었다.** 4단계와 7단계에서 "들어올 때 확인 — 불필요, 공개하기 전에 다시 볼래요"라고 했으므로 인증은 없고 로컬에서만 연다.

## 5. 확인한 것

**(a) 자동 시험(외부 호출은 가짜):** `.venv/bin/python -m pytest -q`

```
...........                                                              [100%]
11 passed in 0.41s
```

시험에 든 것:
- 지역 추천: 날짜만 AI로 나가는지, 지역 이름이 없는 답을 거르는지
- 맛집 검색: 인증 머리글 `KakaoAK`, 검색어, 주소 대체 칸
- **끝에서 끝까지** `POST /api/report`: 추천 · 맛집 · 1일 일정이 모두 있는지. 몸통에 `name`·`phone`을 넣어도 AI와 지도 쪽으로 나가지 않는지("막을 일")
- 맛집이 0개일 때도 리포트가 나오는지
- 빈 날짜와 잘못된 날짜 → 400과 안내
- 열쇠 없음 → 503
- 외부 실패 → 502
- 화면 `GET /`
- 비밀값 검사

**(b) 열쇠 없이 실제로 돌리기:** `env -i PATH=… HOME=… PORT=5077 .venv/bin/python app.py`를 켜고 curl로 불렀다.

```
[경고] OPENAI_API_KEY가 없어요 — .env에 적기 전에는 리포트를 만들 수 없어요.
[경고] KAKAO_REST_API_KEY가 없어요 — .env에 적기 전에는 리포트를 만들 수 없어요.
 * Running on http://127.0.0.1:5077
--- GET /                      → 200
--- POST {"date":"2026-10-10"} → [HTTP 503] {"error":"OPENAI_API_KEY가 없어요 — .env 파일에 OPENAI_API_KEY=... 를 적어 주세요."}
--- POST {}                    → [HTTP 400] {"error":"여행 날짜를 넣어 주세요."}
```

(응답 JSON은 한글을 `\uXXXX`로 이스케이프해 보내므로, 여기에는 풀어서 적었다.)

OpenAI 열쇠만 가짜로 넣었을 때:

```
MissingKeyError: KAKAO_REST_API_KEY가 없어요 — .env 파일에 KAKAO_REST_API_KEY=... 를 적어 주세요.
```

이 경우에도 외부 호출은 일어나지 않았다.

**(c) 고정한 버전으로 불러오고 켜기:** Python 3.14.4 venv에서 `import app, travel, flask, openai, requests, dotenv`가 됐다(`import ok 3.1.3 3.46.0 2.34.2`). `pip check`의 답은 "No broken requirements found."였다. 서버는 위 (b)에서 실제로 켜졌다. openai 3.46.0에 `chat.completions.create`와 `response_format` 인자가 있는 것도 확인했다.

## 6. 확인하지 못한 것

- 실제 OpenAI 응답: 모델 `gpt-4o-mini`가 이 계정에서 열려 있는지, JSON 모드에서 늘 `region` 칸을 주는지.
- 실제 카카오 로컬 응답: 칸 이름(`place_name`, `road_address_name` 등)은 알려진 형식에 맞춰 가짜로 만들었다. 실제 열쇠로 부른 적은 없다. 카카오 개발자 앱의 로컬 API 사용 설정이 필요한지도 확인하지 못했다.
- 브라우저에서 화면을 눈으로 본 적은 없다. `GET /` 200과 HTML 안의 날짜 칸까지만 확인했고, 화면의 JS 렌더링은 시험하지 않았다.
- 리포트가 만들어지는 시간과 맛집 개수의 성공 기준: 원본도 "아직 모름"이라 재지 않았다.
- AI가 돌려준 지역 이름이 카카오 검색에서 맛집을 찾을 만큼 정확한지(예: "강원도 동해안"처럼 넓은 이름).
