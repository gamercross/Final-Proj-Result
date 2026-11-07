# 국내 여행 추천 프로그램 (travel_planner)

여행 날짜를 입력하면 **LLM API**와 **지도 API**를 엮어 국내 여행 리포트를 만들어 주는 CLI 프로그램입니다.

## 개요

```
날짜 입력 ──▶ [1/3] OpenAI (POST)  : 그 시기에 좋은 도시·날씨·행사를 JSON으로 추천
          ──▶ [2/3] Kakao Local (GET): 추천 도시의 맛집 5곳 검색
          ──▶ [3/3] OpenAI (POST)  : 위 데이터를 바탕으로 리포트 본문 작성
          ──▶ results/ 에 JSON · Markdown · HTML 저장
```

- LLM: OpenAI Chat Completions — `POST {OPENAI_BASE_URL}/chat/completions`
- 지도: Kakao Local 키워드 검색 — `GET {KAKAO_BASE_URL}/v2/local/search/keyword.json`
  (머리글 `Authorization: KakaoAK {키}`, 검색어 `"{추천 도시} 맛집"`)
- 1차 추천은 JSON으로만 받습니다. 필수 키: `recommended_city`(문자열), `weather`(문자열),
  `events`(문자열 1~3개), `reason`(문자열). 이 JSON의 `recommended_city`가 다음 단계(맛집 검색)의 입력이 됩니다.
- 리포트의 절 제목과 순서는 프로그램이 정하고, 각 절의 문장만 LLM이 씁니다.
  맛집 목록과 행사 목록은 API 데이터를 그대로 넣으므로 LLM이 식당을 지어내지 않습니다.

## 준비

Python 3.10 이상이 필요합니다.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## API 키 설정

필요한 키는 두 개입니다.

| 환경변수 | 발급처 |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `KAKAO_REST_API_KEY` | https://developers.kakao.com → 내 애플리케이션 → 앱 키 → **REST API 키** (앱 설정에서 카카오맵 사용을 켜야 할 수 있습니다) |

**방법 1 — `.env` 파일 (권장)**

```bash
cp .env.example .env
# .env 파일을 열어 = 뒤에 키를 붙여 넣습니다.
```

**방법 2 — 환경변수 (현재 터미널에서만 유지)**

```bash
# macOS / Linux
export OPENAI_API_KEY="YOUR_KEY"
export KAKAO_REST_API_KEY="YOUR_KEY"
```

```powershell
# Windows PowerShell
$env:OPENAI_API_KEY="YOUR_KEY"
$env:KAKAO_REST_API_KEY="YOUR_KEY"
```

이미 설정된 환경변수가 `.env`보다 우선합니다.

선택 설정: `OPENAI_MODEL`(기본 `gpt-4o-mini`), `OPENAI_BASE_URL`(기본 `https://api.openai.com/v1`),
`KAKAO_BASE_URL`(기본 `https://dapi.kakao.com`).

## 실행 방법

```bash
python travel_planner.py -date 2026-03-15
```

실행 예:

```
[1/3] 1차 추천 생성 중(LLM)...
  - recommended_city: "제주"
[2/3] 맛집 검색 중(지도/장소 API)...
  - 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
  - 리포트 생성 완료

완료! results/2026-03-15_travel_plan.md 를 확인하세요.
  - 원본 데이터: results/2026-03-15_data.json
  - HTML 리포트: results/2026-03-15_travel_plan.html
```

옵션:

- `-date YYYY-MM-DD` (필수, `--date`도 가능) — 형식이 틀리거나 없는 날짜(예: `2026-02-30`)면 사용법을 보이고 종료 코드 2로 끝납니다.
- `--use-cache` (선택) — 같은 날짜의 `results/{date}_data.json`이 있으면 추천·맛집 API를 다시 부르지 않고 그 데이터로 리포트만 다시 만듭니다.

종료 코드: `0` 성공 · `1` 키 미설정 또는 1차 추천 실패 · `2` 날짜 입력 오류

## 결과 확인

`results/` 폴더에 세 파일이 생깁니다.

| 파일 | 내용 |
|---|---|
| `{date}_data.json` | 원본 데이터: `date`, `recommendation`(1차 추천 JSON), `restaurants`(맛집 목록, 0건 가능), `errors`(오류 목록) |
| `{date}_travel_plan.md` | 최종 리포트 (Markdown) |
| `{date}_travel_plan.html` | 최종 리포트 (HTML, 파일 하나로 브라우저에서 바로 열림) |

맛집 항목은 `name`, `address`, `category`, `url`, `x`(경도), `y`(위도)를 가집니다.

리포트 절 순서: `{date} 국내 여행 추천 리포트` → 추천 지역 → 추천 이유 → 날씨 요약 → 행사/축제 →
맛집 추천 → 1일 일정 제안(오전·오후·저녁) → 오류 요약(errors)

```bash
cat results/2026-03-15_travel_plan.md
open results/2026-03-15_travel_plan.html      # Windows: start, Linux: xdg-open
```

## 오류가 났을 때

| 상황 | 동작 |
|---|---|
| API 키 미설정 | 외부 호출 전에 없는 변수 이름과 설정 방법을 보이고 종료(코드 1) |
| 1차 추천 JSON을 읽지 못함 / 필수 키 누락 | "필수 키만 JSON으로" 다시 요청(1회만). 또 실패하면 종료(코드 1) |
| 맛집 검색 0건 | 맛집 = "데이터 없음", errors에 `EMPTY_RESULT`, 계속 진행 |
| 지도 API 401/403 | 〃 `AUTH_ERROR` — 키 값, 카카오맵 사용 설정 확인 |
| 지도 API 429 | 〃 `QUOTA_ERROR` — 잠시 후 재시도, 쿼터 확인 |
| 지도 API 네트워크 오류·기타 HTTP 오류 | 〃 `NETWORK_ERROR` |
| 리포트 LLM 실패 | errors에 `step: "report"`를 남기고, 가진 데이터로 리포트 작성 |

errors 항목 형식: `{"step": "place_search", "type": "AUTH_ERROR", "message": "인증 실패(HTTP 401)"}`

## ⚠️ API 키 유출 주의

- 키를 **코드, README, 커밋, 이슈, 스크린샷, 채팅**에 절대 붙여 넣지 마세요.
- `.env`는 `.gitignore`에 들어 있습니다. `git add .` 전에 `git status`로 `.env`가 빠졌는지 확인하세요.
- `.env.example`에는 변수 이름만 두고 값은 비워 둡니다.
- 프로그램은 화면 출력과 결과 파일에서 키 값을 `***`로 가립니다(오류 메시지에 섞여 와도 가림). 그래도 결과 파일을 공유하기 전에 한 번 더 확인하세요.
- 키가 노출되었다면 **즉시 발급처에서 폐기(재발급)** 하세요. 커밋 기록에 남은 키는 파일을 지워도 남아 있습니다.
- 왜 환경변수로 관리하나요? 공유할 때 실수로 키가 공개되는 것을 막고, 키를 바꿔도 코드를 고칠 필요가 없으며, 과금되는 서비스에서 남의 사용으로 요금이 나오는 사고를 막기 위해서입니다.
