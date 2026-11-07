# Final-Proj-Result

같은 미션(코디세이 AI 활용 미션 1 — **국내 여행 추천 프로그램**: 여행 날짜 → LLM이 지역 추천 → 지도 API로 맛집 → 여행 리포트)을 세 가지 출발점에서 Claude(Opus 5.5)에게 만들게 한 결과를 모았다. 2026-11-07.

| 출발점 | 무엇을 줬나 | 결과 |
|---|---|---|
| **미션 원문만** | 설정 · 스킬 · 메모리가 없는 새 Claude에게 미션 원문 전체 + "이거 만들어줘. 결과는 html로 볼 수 있게도 해줘. API 키는 아직 없어." | [mission-only/](mission-only/README.md) — CLI 프로그램 1,656줄, 시험 19개 통과, 보너스(복수 지역 · 캐시) 포함 |
| [K-Travel-Assistant](https://github.com/gamercross/K-Travel-Assistant) | 사람이 짠 코드(원본은 패키지 이름이 맞지 않아 실행되지 않음) | [from-k-travel/](from-k-travel/build-log.md) — 2줄 고쳐 실행, 시험 9개 통과 |
| [test-1](https://github.com/gamercross/test-1/tree/floe-run-1) | Floe 여덟 단계 문서 27개(코드 없음) | [from-test-1/](from-test-1/build-log.md) — Flask 웹 343줄, 시험 11개 통과 |

## HTML로 보기

| | 파일 | 화면 |
|---|---|---|
| K-Travel-Assistant를 읽고 만든 화면(명령줄 흉내, AI · 지도는 시뮬레이션) | [html/A-k-travel-assistant.html](html/A-k-travel-assistant.html) | [A-screen.png](html/A-screen.png) |
| test-1 문서를 읽고 만든 화면(날짜 → 리포트, AI · 지도는 시뮬레이션) | [html/B-test-1.html](html/B-test-1.html) | [B-screen.png](html/B-screen.png) |
| 미션 원문만 받은 프로그램이 만든 HTML 리포트(키 없는 `--mock` 실행, 2026-11-21) | [html/C-mission-only-report.html](html/C-mission-only-report.html) | [C-screen.png](html/C-screen.png) |

HTML을 만든 Claude의 기록(읽은 파일 · 추측한 것 · 서로 맞지 않는 곳): [build-logs/](build-logs/html-from-test-1.md)

## 숫자

| | 미션 원문만 | K-Travel-Assistant | test-1 |
|---|---:|---:|---:|
| 원본을 읽는 데 드는 입력 토큰 | 4,484 | 3,544 | 55,053 |
| 미션 요구 21개 중 채운 것 | 21 | 16 + 일부 5 | 문서에 2 + 일부 1 |
| 도는 코드로 만들 때 새로 읽은 토큰 · 쓴 토큰 | 59,220 · 45,644 | 71,439 · 12,243 | 128,919 · 18,870 |
| 시험 | 19 통과 | 9 통과 | 11 통과 |

- 토큰은 Claude Opus 5.5 기준. "원본을 읽는 데"는 빈 질문과 파일을 붙인 질문의 입력 토큰 차이, "새로 읽은"은 캐시에 새로 쓴 입력, "쓴"은 출력(생각 포함).
- 진짜 OpenAI · Gemini · Kakao 키로는 아무것도 돌리지 않았다. "시험 통과"는 외부 호출을 가짜로 바꾼 시험이다.
- 각각 한 번씩만 돌렸다.
- 미션 원문(과제 글)은 이 저장소에 싣지 않았다.

## 실행해 보기 (mission-only)

```bash
cd mission-only
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python travel_planner.py --date 2026-03-15 --mock     # 키 없이
python -m unittest -v
```
