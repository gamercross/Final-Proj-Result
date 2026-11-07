# 기준 v1 — 국내 여행 추천 프로그램

미션이 고르게 둔 것을 하나로 정해, 누가 만들든 같은 시험으로 확인한다.

1. Python 3.10 이상. 폴더 맨 위 `travel_planner.py`, 실행은 `python travel_planner.py -date YYYY-MM-DD`. 필요한 패키지는 `requirements.txt`.
2. LLM은 OpenAI Chat Completions — `POST {OPENAI_BASE_URL}/chat/completions`(기본 `https://api.openai.com/v1`), 키 `OPENAI_API_KEY`, 모델 `OPENAI_MODEL`(기본 `gpt-4o-mini`).
3. 지도는 Kakao Local 키워드 검색 — `GET {KAKAO_BASE_URL}/v2/local/search/keyword.json`(기본 `https://dapi.kakao.com`), 머리글 `Authorization: KakaoAK {KAKAO_REST_API_KEY}`, 맛집 5곳.
4. 키는 환경변수(또는 `.env`). 둘 중 하나라도 없으면 외부를 부르기 전에 종료 코드 1로 끝내고, 없는 변수 이름과 설정 방법을 보인다.
5. 날짜가 `YYYY-MM-DD`가 아니면 사용법(usage)을 보이고 종료 코드 2.
6. 1차 추천은 LLM에게 JSON만 받는다 — `recommended_city`(글), `weather`(글), `events`(글 1~3개), `reason`(글). 읽지 못하거나 키가 빠지면 딱 한 번 다시 요청하고, 또 실패하면 종료 코드 1.
7. 맛집은 `recommended_city`로 찾는다. 항목은 `name` · `address` · `category` · `url` · `x` · `y`(숫자). 0건 · 401/403 · 429 · 네트워크 오류여도 멈추지 않고 맛집을 빈 목록으로 두고, errors에 `{"step": "place_search", "type": "EMPTY_RESULT" | "AUTH_ERROR" | "QUOTA_ERROR" | "NETWORK_ERROR", "message": …}`를 남긴다.
8. 최종 리포트는 LLM으로 쓰되 아래 절 제목은 프로그램이 보장한다. 리포트 LLM 호출이 실패하면 errors에 `"step": "report"`를 남기고 가진 데이터로 리포트를 만든다.
9. 저장 — `results/{date}_data.json`(`date` · `recommendation` · `restaurants` · `errors`), `results/{date}_travel_plan.md`, `results/{date}_travel_plan.html`.
10. Markdown과 HTML 모두 이 순서의 절 — `{date} 국내 여행 추천 리포트`(맨 위 제목), `추천 지역`, `추천 이유`, `날씨 요약`, `행사/축제`, `맛집 추천`(0건이면 "데이터 없음"), `1일 일정 제안`(오전 · 오후 · 저녁), `오류 요약(errors)`.
11. HTML은 파일 하나로 열린다 — 바깥 스크립트 · 스타일 · 글꼴을 부르지 않는다. 바깥에서 온 글(LLM · 지도)의 `<` `>`는 그대로 쓰지 않고 이스케이프한다.
12. 진행 로그는 `[1/3]` `[2/3]` `[3/3]` 줄과 끝에 저장 경로(`results/…`)를 보인다.
13. 키 값은 화면 출력과 결과 파일 어디에도 남기지 않는다 — 오류 메시지에 섞여 와도 가린다.
14. `README.md`에 개요 · 실행 방법 · API 키 설정 · 결과 확인 · 키 유출 주의를 쓴다.
