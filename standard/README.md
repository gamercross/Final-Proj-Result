# 기준과 수용 시험

서로 다른 방법으로 만든 결과는 화면도 기능도 제각각이라 나란히 견주기 어렵다. 그래서 **미션 원문을 토대로 기준 하나**([STANDARD.md](STANDARD.md))를 정하고, **어느 구현이든 바깥에서 똑같이 돌리는 시험 24개**를 만들었다.

## 기준이 미션에 더한 것

미션은 고르게 둔 것이 많다(OpenAI 또는 Gemini, Kakao 또는 Naver, 리포트 모양, 파일 이름…). 같은 시험으로 보려고 하나로 정했다.

| 미션 | 기준 v1 |
|---|---|
| LLM은 OpenAI 또는 Gemini | OpenAI Chat Completions, 주소는 `OPENAI_BASE_URL`로 바꿀 수 있게 |
| 지도는 Kakao 또는 Naver | Kakao Local, 주소는 `KAKAO_BASE_URL`로 바꿀 수 있게 |
| 결과 파일 "실행 날짜 기준" | `results/{date}_data.json` · `_travel_plan.md` · `_travel_plan.html` |
| 리포트 항목 | 절 제목 8개와 순서를 고정, Markdown과 HTML 둘 다 |
| 오류 대응 원칙 | 오류 종류 이름(EMPTY_RESULT · AUTH_ERROR · QUOTA_ERROR · NETWORK_ERROR), 끝 코드(키 없음 1 · 날짜 틀림 2) |
| (없음) | HTML은 파일 하나 · 바깥 글 이스케이프, 키는 출력 · 파일에 남기지 않기 |

주소를 바꿀 수 있어야 진짜 키 없이 **가짜 OpenAI · Kakao 서버**([acceptance/fake_server.py](acceptance/fake_server.py))로 돌릴 수 있다.

## 시험 24개

구현 안은 보지 않는다. 새 빈 폴더에서 `python travel_planner.py -date 2026-11-21`로 돌리고 끝 코드 · 화면 글 · `results/` 파일 · 가짜 서버가 받은 요청만 본다. 이름 앞 번호는 기준의 번호다.

| 시험 | 무엇을 보나 |
|---|---|
| `01` 세 파일 | 끝 코드 0, `results/`에 json · md · html |
| `12` 진행 로그 | 화면에 `[1/3]` `[2/3]` `[3/3]`, `results/` 경로 |
| `09` JSON 모양 | `date` · `recommendation`(네 키, 행사 1~3개) · `restaurants` · `errors`(빈 목록) |
| `07` 맛집 모양 | 5곳, `name` · `address` · `category` · `url` · `x` · `y`(숫자), 지도가 준 순서 |
| `02 · 03` 부르는 법 | OpenAI에 `Bearer` 키로 1번, Kakao에 `KakaoAK` 키로 추천 도시를 검색어에 넣어 1번, 리포트도 LLM으로 |
| `10` Markdown 절 | 맨 위 제목 + 일곱 절이 순서대로, 도시 · 행사 · 맛집 5곳 · 오전/오후/저녁이 제 절에 |
| `10` HTML 절 | HTML도 같은 제목과 순서, 맛집 5곳 |
| `11` HTML 한 파일 | 바깥 스크립트 · 스타일 · 글꼴을 부르지 않음 |
| `11` 이스케이프 | LLM이 `<script>` · `<b>`를 섞어 보내도 HTML에 그대로 쓰지 않음 |
| `05` 날짜 틀림 | 끝 코드 2, usage, 바깥을 부르지 않음 |
| `04` 키 없음 ×2 | `OPENAI_API_KEY` · `KAKAO_REST_API_KEY` 각각 — 끝 코드 1, 변수 이름을 보임, 바깥을 부르지 않음 |
| `06` 재시도 ×2 | JSON이 아님 · 키가 빠짐 → 딱 한 번 더 묻고 성공 |
| `06` 두 번 실패 | 1차 추천을 정확히 2번 묻고 끝 코드 1, 지도는 부르지 않음 |
| `07` 0건 | 계속 진행, `EMPTY_RESULT`, 맛집 절에 "데이터 없음" |
| `07` 401 · 403 | `AUTH_ERROR`로 계속 |
| `07` 429 | `QUOTA_ERROR`로 계속 |
| `07` 네트워크 | 닫힌 주소 → `NETWORK_ERROR`로 계속 |
| `08` 리포트 실패 | 리포트 LLM이 500이어도 절이 다 있는 리포트 + `errors`에 `report` |
| `10` 오류 절 | 401일 때 "오류 요약(errors)" 절에 `AUTH_ERROR` |
| `13` 키 숨김 | Kakao 오류 본문에 키가 섞여 와도 화면 · 결과 파일에 키가 없음 |
| `14` README | 키 이름 두 개, `-date`, `results`, 유출 주의 |

## 돌리는 법

```bash
bash standard/run.sh <구현 폴더>          # 새 가상환경에 그 구현의 requirements.txt + pytest를 깔고 24개
```

[reference/](reference/travel_planner.py)는 **시험이 맞게 짜였는지 확인하려고 만든 가장 작은 구현**(표준 라이브러리만)이다 — 24개를 모두 통과한다. 비교 대상이 아니다.

## 시험을 고친 기록

| 날짜 | 무엇 | 왜 |
|---|---|---|
| 2026-11-07 | `09` JSON 모양 — 정상 흐름의 `errors`가 빈 목록이어야 한다 → **`report` 단계 오류는 세지 않음** | "Claude만" 구현을 처음 돌렸을 때 이 시험만 실패했다. 그 구현은 리포트 문장을 LLM에게 JSON으로 받는데 가짜 서버가 Markdown으로 답해 `report` · `PARSE_ERROR`가 남았다. 리포트 응답 모양은 기준이 정하지 않은 것이라 시험 장치의 가정 탓으로 봤다. 고친 뒤 기준 구현 24/24 그대로 |

## 한계

- 가짜 서버의 답은 정해져 있다. 진짜 OpenAI · Kakao가 다르게 답하는 경우(모델이 JSON 모드를 무시하는 등)는 보지 않는다.
- 1차 추천 요청과 리포트 요청은 요청 글에 추천 도시("단양")가 있는지로 가른다.
- K-Travel(Gemini) · test-1 첫 실행(Flask 웹) · 미션 원문만(주소가 코드에 박힘)은 기준 이전에 만든 것이라 이 시험으로 돌릴 수 없다 — 그쪽은 미션 요구 21개 표로 본다.
