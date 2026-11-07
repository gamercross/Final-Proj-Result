# build-log — K-Travel-Assistant → index.html

## 1. 읽은 파일

폴더 안 파일은 9개(합계 약 8KB)이고, 모두 끝까지 읽었다. 한 번에 아래 차례로 열었다.

1. `README.md` — 전부
2. `requirements.txt` — 전부
3. `.gitignore` — 전부
4. `travel_planner.py` — 전부
5. `src/__init__.py` — 전부(빈 파일)
6. `src/config.py` — 전부
7. `src/kakao_client.py` — 전부
8. `src/gemini_client.py` — 전부
9. `src/report_generator.py` — 전부(빈 파일)

## 2. 무엇을 만드는지 이해한 것

이 프로그램은 CLI 하나다(`python travel_planner.py -date YYYY-MM-DD`). 날짜를 검사하고, 환경변수에서 Gemini · Kakao 키를 확인한 뒤 세 단계를 돈다. [1/3]에서는 Gemini에 날짜를 주고 `{recommended_city, weather, events, reason}` JSON을 받는다. 실패하면 한 번 다시 하고, 또 실패하면 끝낸다. [2/3]에서는 Kakao Local 키워드 검색으로 "`<도시> 맛집`" 5곳을 찾는다. 실패하거나 0건이면 경고만 남기고 빈 목록으로 계속한다. [3/3]에서는 Gemini가 마크다운 리포트(1일 일정 오전/오후/저녁 포함)를 쓴다. 결과는 `results/<날짜>_data.json`(date · recommendation · restaurants · errors)과 `results/<날짜>_travel_plan.md` 두 파일에 저장한다. README는 한 줄 설명이 "…"로 끊겨 있어 거의 도움이 안 됐다. `travel_planner.py`의 `main()` 1~85줄, 특히 `[1/3]·[2/3]·[3/3]` print와 `errors` 리스트를 읽은 시점에 무엇을 만들지 분명해졌다. 화면은 "명령 실행 → 터미널 출력 → results 폴더의 두 파일"을 그대로 보여 주는 모양으로 정했다.

## 3. 구현한 기능

| 기능 | 출처(file + section/line) | 그대로/바꿈 |
|---|---|---|
| `-date` 인자 입력과 실행 | travel_planner.py 12–14 | 바꿈 — CLI 대신 글 칸 + 실행 단추. 명령 모양은 화면에 그대로 둠 |
| 날짜 검증(`strptime "%Y-%m-%d"`)과 실패 문구 · 종료 | travel_planner.py 17–21 | 그대로 — Python strptime 규칙(한 자리 월·일 허용, 없는 날짜 거부)을 정규식 + 달력 검사로 옮김 |
| API 키 확인과 안내 문구(GEMINI 먼저, KAKAO 다음) | src/config.py 7–21 | 바꿈 — 환경변수 대신 "설정됨" 체크박스(값은 받지 않음) |
| [1/3] 1차 추천, 실패 시 1회 재시도, 최종 실패 시 종료 | travel_planner.py 31–44 | 그대로(응답은 시뮬레이션) |
| 추천 응답 JSON 풀기, ``` 감싸기 벗기기, JSON_PARSE_ERROR / API_ERROR | src/gemini_client.py 27–39 | 그대로 — `split("```")[1].replace("json","")`도 같은 방식으로 옮김 |
| [2/3] 맛집 검색 "`<도시> 맛집`", 5곳, 결과 필드 name·address·category·url·x·y | src/kakao_client.py 9–54 | 바꿈 — 실제 호출 대신 예시 5곳 생성 |
| 맛집 오류 분기: 401/403 AUTH_ERROR, EMPTY_RESULT, NETWORK_ERROR → 경고 후 빈 목록으로 계속 | src/kakao_client.py 32–57, travel_planner.py 51–56 | 그대로(고르는 칸으로 흉내) |
| [3/3] 리포트 생성(맛집 없으면 "- 데이터 없음"), 오류 처리 없음 → 멈춤 | src/gemini_client.py 41–64, travel_planner.py 59–60 | 바꿈 — LLM 글 대신 프롬프트 요구(제목·소제목·bullet·오전/오후/저녁)를 따른 고정 틀 |
| `results/<날짜>_data.json`, `results/<날짜>_travel_plan.md` 저장 | travel_planner.py 62–80, README "결과 확인" | 바꿈 — 디스크 대신 화면에 미리 보기 + 내려받기 |
| 완료 문구(✅ 완료!, JSON/리포트 경로) | travel_planner.py 82–84 | 그대로 |
| 응답에 키가 없으면(예: recommended_city) 처리되지 않은 예외로 멈춤 | travel_planner.py 44, gemini_client.py 54–57(검증 없음) | 그대로 — "Traceback (시뮬레이션)"으로 표시 |

## 4. 추측한 것

1. **응답을 흉내 내는 방법.** 1차 추천은 사람이 고칠 수 있는 JSON 글 칸(기본값은 "제주" 예시)으로, 오류는 고르는 칸(정상 / 첫 시도 실패 / 두 번 실패)으로 흉내 냈다. 원본은 LLM이 무엇을 답할지 정하지 않으므로, 내용을 지어내지 않고 코드의 분기를 모두 보여 주는 가장 작은 방법을 골랐다.
2. **예시 맛집 이름 · 주소.** "(예시) 제주 맛집 1" 같은 자리 표시 글로 했다. 실제 가게 이름을 지어내면 거짓 정보가 된다. category는 "음식점", url은 "", x·y는 0.0으로 두었다. 원본은 Kakao 응답에서 이 값을 받으므로 예시 값이 없다.
3. **리포트 본문.** LLM이 자유롭게 쓰는 글이라 원본에 정해진 모양이 없다. 프롬프트에 적힌 재료(지역·이유·날씨·행사·맛집)와 형식 요구(제목·소제목·bullet, 1일 일정 오전/오후/저녁)만 넣은 고정 틀로 만들었다. 리포트 첫머리에 "시뮬레이션" 표시를 넣었다. 날짜는 넣지 않았는데, `generate_report`가 날짜를 받지 않기 때문이다.
4. **리포트 단계의 실패 옵션.** 원본에는 처리 코드가 없지만 실제 API는 실패할 수 있다. 그래서 고르는 칸을 하나 두고, 실패하면 원본처럼 파일 없이 멈추게 했다.
5. **환경변수는 체크박스로.** 과제 규칙("API 키 없음")과 README의 "값은 절대 공개하지 마세요"에 맞춰 값을 받지 않고 "설정됨 / 안 됨"만 고르게 했다.
6. **results 폴더는 페이지 안 메모리.** 실행할 때마다 쌓이고, 같은 날짜면 덮어쓴다. 원본의 `makedirs(exist_ok=True)`와 같은 파일 이름 쓰기를 흉내 낸 것이다. 새로고침하면 사라진다.
7. **`events`가 리스트가 아닐 때.** Python `', '.join(문자열)`은 글자마다 나눠 잇는다. 이 동작을 그대로 따라 했다. 숫자처럼 반복할 수 없는 값이면 TypeError로 멈추게 했다.
8. **네트워크 오류 메시지 글.** 원본은 `str(e)`라 내용이 정해져 있지 않다. "(시뮬레이션) 연결 시간 초과(timeout=10)"로 두었다.
9. **리포트 미리 보기는 마크다운 원문 그대로.** 원본은 .md 파일을 저장할 뿐 화면에 그리지 않는다.

## 5. 서로 맞지 않는 곳

1. `requirements.txt`는 `google-generativeai==0.4.0`인데 `src/gemini_client.py` 2줄은 `import google.genai as genai`다(다른 패키지). 그 뒤에 쓰는 `genai.configure` · `genai.GenerativeModel`은 `google.generativeai` 쪽 API라서, 적힌 대로 설치하면 import에서 멈춘다.
2. `src/report_generator.py`는 빈 파일이다. 리포트 생성은 실제로 `GeminiClient.generate_report`가 한다. 이름만 있는 모듈이다.
3. 오류 처리가 고르지 않다. 1차 추천은 오류를 잡고 재시도하고, 맛집은 경고 후 계속한다. 그런데 최종 리포트(`generate_report`)는 try가 없어 실패하면 traceback으로 멈추고 errors에도 남지 않으며 파일도 저장되지 않는다. 1차 추천 응답에 키가 빠졌을 때도 검증 없이 KeyError로 멈춘다.
4. `travel_planner.py` 63줄 `date_str = args.date.replace("-", "")`는 만들기만 하고 쓰지 않는다. 파일 이름에는 `args.date`를 쓴다. 18줄의 `travel_date`도 검증 말고는 쓰지 않는다.
5. 날짜 형식 표시는 "YYYY-MM-DD"인데, `strptime`이 "2024-3-5"도 받아 들인다. 그러면 파일 이름이 `2024-3-5_data.json`이 되어 README의 `YYYY-MM-DD_data.json`과 어긋난다.
6. 맛집 EMPTY_RESULT는 `[]`와 err를 함께 돌려준다. 그러나 main은 err만 보고 "경고"로 처리하므로 빈 목록이 성공인지 오류인지 반환 규약이 섞여 있다. 401/403/네트워크는 `None`을 돌려준다.
7. ``` 벗기기의 `.replace("json", "")`는 앞의 언어 표시만이 아니라 본문 안의 모든 "json" 글자도 지운다(예: reason 안의 "json"). 주석("JSON 파싱")이 의도한 동작과 다르다.
8. `.gitignore`에 `.env`가 두 번 있다. README 첫 설명 줄은 "…를 조합하여..."에서 끊겨 있다. README 결과 파일 이름은 `\``로 이스케이프되어 마크다운에서 백틱이 그대로 보인다.
9. README는 `export`로 환경변수를 설정하라고만 한다. 그런데 `config.py`는 `load_dotenv()`로 `.env` 파일도 읽는다. `.env` 사용법은 README에 없다(보안 주의에만 이름이 나온다).

## 6. HTML로 못 한 것

| 원본이 요구하는 것 | 한 것 |
|---|---|
| Google Gemini API 호출(1차 추천, 최종 리포트) | 호출하지 않는다. 추천은 사람이 고칠 수 있는 JSON 글, 리포트는 고정 틀로 흉내 냈다. 화면과 리포트에 "시뮬레이션"이라고 표시했다 |
| Kakao Local API 키워드 검색 | 호출하지 않는다. "(예시)"가 붙은 5곳과 오류 분기(401/403/0건/네트워크)를 고르는 칸으로 흉내 냈다 |
| 환경변수 · `.env`에서 API 키 읽기 | 키 값은 받지 않고 "설정됨" 체크박스만 둔다 |
| `results/` 폴더에 파일 쓰기 | 페이지 안에 미리 보기를 두고 Blob으로 내려받게 했다. 영구 저장은 하지 않는다 |
| CLI 실행 · 종료 코드 · traceback | 터미널 모양 칸에 같은 print 문구를 내고 "(종료 코드 1)" / "Traceback (시뮬레이션)"으로 표시한다 |

## 7. 군더더기

읽은 양은 약 8KB(코드 약 6.5KB, 문서 약 1.5KB)이고, 만드는 데 쓸모 있던 비율은 **약 85%** 다.
- 쓸모 있었다: `travel_planner.py`, `kakao_client.py`, `gemini_client.py`, `config.py`는 거의 모든 줄이 화면 문구 · 분기 · 데이터 모양으로 바로 이어졌다.
- 쓸모 없거나 겹쳤다(약 15%):
  - 빈 파일 둘(`__init__.py`, `report_generator.py`)
  - 설치 · OS별 키 설정 안내(README의 macOS/Windows 블록)
  - `requirements.txt`
  - `.gitignore`의 중복 줄
  - 쓰지 않는 변수(`date_str`)
  - 같은 내용을 두 번 쓴 키 확인 블록
- README는 결과 파일 이름 확인 말고는 거의 보탬이 없었다(설명 줄이 끊김).

## 8. 이해하기 쉬웠던 정도

**4 / 5**
1. 코드가 짧고 순서가 하나라서 흐름을 오해할 여지가 없다. print 문구와 errors 구조(`step`·`type`·`message`)가 그대로 화면 스펙 역할을 했다.
2. 오류 분기가 코드에 모두 드러나 있었다(401/403/0건/네트워크, 재시도 1회, JSON 실패). 무엇을 흉내 내야 하는지 추측할 필요가 없었다.
3. 감점 이유: 핵심 내용(추천 도시, 리포트 본문)은 외부 LLM · API가 정해서 원본에 예시가 없다. README의 목적 설명은 끊겨 있다. 패키지 불일치 · 빈 모듈 · 처리 안 된 리포트 오류처럼 "의도가 무엇이었나"를 짐작해야 하는 곳이 몇 군데 있다.

## 참고 — 원본 안의 지시

폴더 안에 이 작업 밖의 행동(커밋 · 푸시 · 사람에게 묻기 등)을 요구하는 글은 없었다. README의 설치 · 키 설정 · 실행 안내는 제품 사용법으로만 읽었고 실행하지 않았다.
