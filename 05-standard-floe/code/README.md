# test-1
코디세이 AI 활용 학습의 미션 1의 문제를 floe가 작업한 내용들을 기록한 repo이다

이전 기록(2026-10-28 ~ 11-04 첫 번째 실행)은 [floe-run-1](https://github.com/gamercross/test-1/tree/floe-run-1) 브랜치에 있다.

## 프로그램 개요

여행 날짜를 넣으면 ① AI(OpenAI)가 그 시기에 좋은 국내 지역을 추천하고 ② 지도(Kakao Local)로 그 지역 맛집을 찾아 ③ AI로 여행 리포트(Markdown · HTML)를 써서 원본 데이터(JSON)와 함께 `results/`에 남기는 CLI 프로그램이에요. 지금은 **6단계** — 지역 추천 · 맛집 찾기 · 리포트를 하나씩 만들고 시험으로 확인했어요.

## 실행하는 법

```bash
pip install -r requirements.txt && python travel_planner.py -date 2026-03-15
```

- 예시 입력: `-date 2026-03-15` (형식은 `YYYY-MM-DD`, 틀리면 사용법을 보이고 종료 코드 2)
- 키가 없으면 외부를 부르기 전에 종료 코드 1로 끝나고, 없는 변수 이름과 설정 방법을 보여 줘요.

**키 없이 흐름만 확인하기** — 로컬 가짜 서버(가짜 데이터, 실제 API 안 부름)로 돌려 봐요.

```bash
python tests/fake_server.py &
OPENAI_API_KEY=dummy KAKAO_REST_API_KEY=dummy OPENAI_BASE_URL=http://127.0.0.1:8765 KAKAO_BASE_URL=http://127.0.0.1:8765 python travel_planner.py -date 2026-03-15
```

**시험 코드 돌리기** — 실제 API 없이 확인해요.

```bash
python -m unittest discover -s tests -v
```

- `tests/test_recommend.py` — 지역 추천: 날짜를 넣으면 지역 이름이 나와야 해요(6단계). 읽지 못하거나 키 · 타입이 어긋나면 딱 한 번 다시 요청하고, 또 실패하면 종료 코드 1.
- `tests/test_restaurants.py` — 맛집 찾기: 지역을 넣으면 맛집 목록이 나와야 해요(6단계). 0건 · 401/403 · 429 · 네트워크 오류여도 멈추지 않고 빈 목록 + errors(`EMPTY_RESULT` · `AUTH_ERROR` · `QUOTA_ERROR` · `NETWORK_ERROR`)로 남고, 리포트는 '데이터 없음'으로 계속 만들어져요.
- `tests/test_report.py` — 리포트: 결과를 넣으면 한 장이 나와야 해요(6단계). Markdown · HTML 모두 기준 10 순서의 절, HTML은 파일 하나로 열리고 바깥 글의 `<` `>`를 이스케이프. 리포트 AI가 실패해도 errors에 `"step": "report"`를 남기고 가진 데이터로 한 장을 만들어요.

2026-11-07에 이 명령으로 돌려 `results/2026-03-15_data.json`, `results/2026-03-15_travel_plan.md`가 생기는 것을 확인했어요. 실제 키로는 아직 돌려 보지 않았어요.

## API 키 설정

1. `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`, `KAKAO_REST_API_KEY` 값을 채워요(또는 `export`로 환경변수 설정).
2. 선택: `OPENAI_MODEL`(기본 `gpt-4o-mini`), `OPENAI_BASE_URL`, `KAKAO_BASE_URL`.

## 결과 확인

- `results/{날짜}_travel_plan.md` — 여행 리포트
- `results/{날짜}_travel_plan.html` — 같은 리포트를 브라우저로(파일 하나로 열려요)
- `results/{날짜}_data.json` — `date` · `recommendation` · `restaurants` · `errors`

## 키 유출 주의

- 키는 `.env`나 환경변수에만 두고 코드 · README · 결과 파일에 쓰지 않아요.
- `.env`와 `results/`는 `.gitignore`에 들어 있어요. 올리기 전에 `git status`로 `.env`가 없는지 확인해요.

## 할 일

- [x] LLM 추천 JSON을 읽지 못하거나 키가 빠지면 딱 한 번 다시 요청, 또 실패하면 종료 코드 1 (기준 6) — 2026-11-07, `tests/test_recommend.py`
- [x] 지도 오류를 `AUTH_ERROR`(401/403) · `QUOTA_ERROR`(429) · `NETWORK_ERROR`로 나눠 errors에 남기기 (기준 7) — 2026-11-07, `tests/test_restaurants.py`
- [x] 최종 리포트를 LLM으로 쓰기 + 실패 시 `"step": "report"` 남기고 가진 데이터로 만들기 (기준 8) — 2026-11-07, `tests/test_report.py`. LLM은 `추천 이유` 요약과 `1일 일정 제안`을 쓰고, 절 제목 · 지역 · 날씨 · 행사 · 맛집 · errors는 프로그램이 채워요
- [x] `1일 일정 제안`(오전 · 오후 · 저녁) 채우기 (기준 10) — 2026-11-07, 리포트 AI가 실패하면 '데이터 없음'
- [x] `results/{date}_travel_plan.html` — 파일 하나로 열리고 바깥 글의 `<` `>` 이스케이프 (기준 9 · 11) — 2026-11-07
- [ ] 키 값이 오류 메시지에 섞여 와도 화면 · 파일에서 가리기 (기준 13)
- [x] 추천 JSON 값의 타입 검사(events는 글 1~3개 등) — 타입이 어긋나도 '읽지 못함'으로 보고 한 번 다시 요청해요. `reason` 2~4문장은 세지 않아요(아래 '정할 것')
- [ ] 실제 키로 한 번 돌려 보기
- [ ] (보너스) 복수 지역 추천 · 같은 날짜 결과 캐싱

## 정할 것

- **CLI인가, 서버가 있는 웹인가** — 4단계 결정은 "서버가 있는 웹"인데, 받은 글의 기준 v1(1 · 12번)과 미션은 CLI(`python travel_planner.py -date …`, 웹 UI 요구 안 함)예요. 뼈대는 기준에 맞춰 CLI로 만들었어요. 웹 화면을 더할지: ____
- **API 요청 제한 시간(초)** — 문서에 없어 코드에 임시로 20초를 두었어요(`TIMEOUT_SEC`). 정할 값: ____
- **맛집 검색어** — 문서에는 "`recommended_city`로 찾는다"만 있어 임시로 `"{지역} 맛집"`을 써요. 정할 검색어: ____
- **401/403/429 말고 다른 HTTP 오류(예: 500)의 type** — 기준 7은 네 가지 type만 말해요. 지금은 `NETWORK_ERROR`(message `HTTP 500`)로 남겨요. 정할 것: ____
- **지도 오류 때 다시 요청할까** — 기준에 없어 지금은 다시 요청하지 않아요. 정할 것: ____
- **추천 요청이 네트워크 · HTTP 오류로 실패할 때 다시 요청할까** — 기준 6은 "읽지 못하거나 키가 빠지면"만 말해요. 지금은 다시 요청하지 않고 바로 종료 코드 1. 정할 것: ____
- **`reason` 2~4문장을 검사할까** — 문장 세는 법이 문서에 없어 지금은 글인지만 봐요. 정할 것: ____
- **리포트 AI 오류의 type** — 기준 8은 `"step": "report"`만 말해요. 지금은 지도와 같은 `AUTH_ERROR` · `QUOTA_ERROR` · `NETWORK_ERROR`, 읽지 못하면 임시 이름 `PARSE_ERROR`를 써요. 정할 것: ____
- **리포트 AI가 실패할 때 다시 요청할까** — 기준에 없어 지금은 다시 요청하지 않고 가진 데이터로 만들어요. 정할 것: ____
- **리포트 AI에게 맡길 몫** — 지금은 `추천 이유` 요약과 `1일 일정 제안`만 맡기고 나머지는 프로그램이 채워요(맛집 목록 · errors가 바뀌지 않게). 더 맡길지: ____
- **언제 성공인가** — 2단계에서 "아직 모름". 성공 기준: ____
- **화면 원칙** — 4단계에서 "아직 모름": ____

<!-- floe:start -->
## 버전 기록

**지금 버전: V.8** — 관문을 하나 넘을 때마다 하나 올라요(C-23).

- V.1 · 2026-11-07 · 1단계 무엇을 만들지 정하기 관문 — 여행 날짜에 어디가 좋은지, 어디서 먹을지 하나하나 찾기 어려워요.
- V.2 · 2026-11-07 · 2단계 아이디어 적어 두기 관문 — 누구: 여행 날짜를 넣는 사용자 · 불편: 어디가 좋은지, 어디서 먹을지 하나하나 찾기 어려워요 · 해결: 날짜만 넣으면 추천 지역과 맛집 리포
- V.3 · 2026-11-07 · 3단계 꼭 필요한 기능 정리하기 관문 — 여행 날짜를 넣으면, 앱은 좋은 지역을 추천한다 / 지역이 정해지면, 앱은 그 지역의 맛집을 찾는다 / 결과가 모이면, 앱은 여행 리포트를 만든
- V.4 · 2026-11-07 · 4단계 만드는 방법 고르기 관문 — 서버가 있는 웹 / 화면 하나짜리 웹 / 휴대폰 앱
- V.5 · 2026-11-07 · 5단계 뼈대 먼저 이어 보기 관문 — ① 여행 날짜 넣기 → ② AI가 좋은 지역 추천 → ③ 지도로 맛집 찾기 → ④ 여행 리포트 보여 주기
- V.6 · 2026-11-07 · 6단계 하나씩 만들고 확인하기 관문 — 지역 추천 — 날짜를 넣으면 지역 이름이 나와야 해요 / 맛집 찾기 — 지역을 넣으면 맛집 목록이 나와야 해요 / 리포트 — 결과를 넣으면 한 
- V.7 · 2026-11-07 · 7단계 실제로 써 보고 재 보기 관문 — 지역 추천: 날짜 넣고 지역 이름 나오나 / 맛집 찾기: 지역 넣고 목록 나오나 / 리포트: 한 장 나오나
- V.8 · 2026-11-07 · 8단계 돌아보고 배운 것 남기기 관문 — 잘된 점: 시험 27개가 통과했어요 · 아쉬운 점: 실제 열쇠로는 아직 안 돌려 봤어요.

## 계획 (Floe)

**국내 여행 추천 프로그램** — Floe의 여덟 단계로 만들어요.

- 기획서: [docs/PRD.md](docs/PRD.md)
- 결정 기록: [docs/decisions.md](docs/decisions.md)
- 1단계 무엇을 만들지 정하기: [docs/01-idea/idea.md](docs/01-idea/idea.md)
- 2단계 아이디어 적어 두기: [docs/02-plan/plan.md](docs/02-plan/plan.md)
- 3단계 꼭 필요한 기능 정리하기: [docs/03-requirements/requirements.md](docs/03-requirements/requirements.md)
- 4단계 만드는 방법 고르기: [docs/04-design/design.md](docs/04-design/design.md)
- 5단계 뼈대 먼저 이어 보기: [docs/05-skeleton/skeleton.md](docs/05-skeleton/skeleton.md)
- 6단계 하나씩 만들고 확인하기: [docs/06-build/build.md](docs/06-build/build.md)
- 7단계 실제로 써 보고 재 보기: [docs/07-measure/measure.md](docs/07-measure/measure.md)
- 8단계 돌아보고 배운 것 남기기: [docs/08-retro/retro.md](docs/08-retro/retro.md)
- 단계 폴더 목차: [docs/README.md](docs/README.md)
<!-- floe:end -->
