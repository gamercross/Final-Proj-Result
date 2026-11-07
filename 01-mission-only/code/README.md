# 국내 여행 추천 프로그램 (LLM API + 지도 API)

여행 날짜를 입력하면

1. **LLM API**(OpenAI 또는 Gemini)가 그 시기에 가기 좋은 국내 지역·날씨·행사를 **JSON**으로 추천하고
2. 추천된 지역 이름으로 **Kakao Local API**에서 맛집을 검색한 뒤
3. 다시 **LLM API**가 두 데이터를 합쳐 최종 여행 리포트(Markdown)를 작성합니다.

결과는 `results/` 폴더에 **원본 JSON + Markdown 리포트 + HTML 리포트**로 저장됩니다.

```
날짜 ──▶ [1] LLM 1차 추천 (JSON) ──▶ [2] Kakao 맛집 검색 ──▶ [3] LLM 최종 리포트 ──▶ results/
           POST /chat/completions       GET /v2/local/search/keyword.json   POST
```

## 폴더 구조

```
travel_planner.py      # CLI 진입점 (argparse, 전체 흐름, 결과 저장, 캐시)
planner/
  config.py            # .env / 환경변수에서 설정·키 읽기, 키 미설정 안내
  errors.py            # 공통 HTTP 호출, 오류 분류(AUTH/QUOTA/NETWORK/PARSE...), 오류 목록, 키 마스킹
  llm.py               # OpenAI·Gemini 클라이언트, 1차 추천 프롬프트, JSON 파싱/검증/재시도
  places.py            # Kakao Local 맛집 검색, 결과 정규화
  report.py            # 최종 리포트 프롬프트, 섹션 검증, 오류 섹션, HTML 변환
  mock.py              # API 키 없이 흐름을 확인하는 가짜 클라이언트
tests/test_planner.py  # 키 없이 돌아가는 테스트 (가짜 HTTP 응답으로 오류 정책 검증)
.env.example           # 설정 파일 예시 (실제 키 없음)
```

## 설치

Python 3.10 이상이 필요합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## API 키 설정

### 1. 키 발급

| 용도 | 서비스 | 발급 위치 | 환경변수 |
| --- | --- | --- | --- |
| LLM (택1) | OpenAI | https://platform.openai.com/api-keys (유료, 결제 수단 등록 필요) | `OPENAI_API_KEY` |
| LLM (택1) | Google Gemini | https://aistudio.google.com/apikey (무료 티어 있음) | `GEMINI_API_KEY` |
| 지도 | Kakao Local | https://developers.kakao.com → 내 애플리케이션 → 앱 추가 → **REST API 키** | `KAKAO_REST_API_KEY` |

> **Kakao 주의:** 앱을 만든 뒤 콘솔의 **[제품 설정 → 카카오맵]** 에서 사용 설정을 **ON** 해야 합니다.
> 꺼져 있으면 키가 맞아도 `403`(AUTH_ERROR)이 납니다.

### 2. 키 넣기 (택1)

**방법 A — `.env` 파일 (권장)**

```bash
cp .env.example .env
# .env 를 열어 값을 채운다. Gemini를 쓰려면 LLM_PROVIDER=gemini 로 바꾼다.
```

**방법 B — 환경변수 (현재 터미널 세션에만 적용)**

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

환경변수가 이미 설정되어 있으면 `.env`보다 우선합니다. 필요한 키가 없으면 프로그램은 API를 호출하지 않고 즉시 종료하면서 설정 방법을 출력합니다.

## 실행 방법

```bash
python travel_planner.py -date "2026-03-15"
```

```
[1/3] 1차 추천 생성 중(LLM)...
    - recommended_city: "제주"
[2/3] 맛집 검색 중(지도/장소 API)...
    - 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
    - 리포트 생성 완료

완료! results/2026-03-15_travel_plan.md 를 확인하세요.
      HTML: results/2026-03-15_travel_plan.html
      원본 JSON: results/2026-03-15_raw.json
```

| 옵션 | 설명 |
| --- | --- |
| `-date` / `--date YYYY-MM-DD` | **필수.** 여행 날짜. 형식이 틀리면 사용법을 출력하고 종료 |
| `--cities 1~3` | 추천 지역 수 (기본 1). 2~3이면 지역별로 맛집을 검색하고 리포트도 지역별로 정리 *(보너스)* |
| `--places N` | 지역당 맛집 수 (기본 5, 최대 15) |
| `--no-cache` | 같은 날짜의 결과가 있어도 API를 다시 호출 |
| `--mock [all\|llm\|places]` | API 키 없이 예시 데이터로 실행. `llm`/`places`로 한쪽만 가짜로 대체 가능 |
| `--out-dir DIR` | 결과 폴더 (기본 `results`) |

### 키 없이 먼저 돌려보기

```bash
python travel_planner.py --date 2026-03-15 --mock              # 전부 예시 데이터
python travel_planner.py --date 2026-03-15 --mock llm          # Kakao 키만 있을 때: LLM만 가짜
python travel_planner.py --date 2026-10-10 --mock --cities 3   # 복수 지역 (보너스)
```

mock 모드도 실제 모드와 **같은** JSON 파싱·검증·리포트·저장 코드를 거칩니다. HTML에는 "MOCK 모드" 표시가 붙습니다.

## 결과물 확인 방법

`results/` 폴더에 여행 날짜 기준으로 파일이 저장됩니다.

| 파일 | 내용 |
| --- | --- |
| `YYYY-MM-DD_raw.json` | 원본 데이터: `recommendation`(1차 추천 JSON), `restaurants`(도시별 맛집 검색 결과, 0건 가능), `errors`(오류 요약 배열), `report_markdown`, `meta` |
| `YYYY-MM-DD_travel_plan.md` | 최종 리포트 (추천 지역 / 추천 이유 / 날씨 요약 / 행사·축제 / 맛집 추천 / 1일 일정 제안 / 오류 요약) |
| `YYYY-MM-DD_travel_plan.html` | 위 리포트를 브라우저로 보기 좋게 렌더링한 파일 |

```bash
open results/2026-03-15_travel_plan.html      # macOS
start results\2026-03-15_travel_plan.html     # Windows
```

## 오류 처리 정책

모든 API 호출은 `planner/errors.py`의 `request_json()`을 거치고, 실패는 아래처럼 분류되어 `errors` 목록(원본 JSON과 리포트의 "오류 요약")에 남습니다.

| 상황 | 분류 | 동작 |
| --- | --- | --- |
| API 키 미설정 | — | 즉시 종료 + 설정 방법 안내 (exit 1) |
| 401 / 403 | `AUTH_ERROR` | 키 값, 권한, (Kakao) 카카오맵 활성화 확인 |
| 429 | `QUOTA_ERROR` | 호출 한도 / 잔액 확인 |
| 타임아웃, 연결 실패 | `NETWORK_ERROR` | 네트워크 확인 |
| 5xx / 기타 4xx | `SERVER_ERROR` / `HTTP_ERROR` | |
| JSON 아님, 구조 다름 | `PARSE_ERROR` | |
| 필수 키/타입 불일치 | `VALIDATION_ERROR` | |
| 맛집 검색 0건 | `EMPTY_RESULT` | |

- **지도 API 실패·0건** → 맛집 섹션을 "데이터 없음"으로 표기하고 리포트 생성은 계속합니다.
- **1차 추천 JSON 파싱 실패** → "필수 키만 JSON으로 다시 출력하라"는 프롬프트로 **딱 1회만** 재시도합니다. 그래도 실패하면 추천 지역이 없어 다음 단계로 갈 수 없으므로 오류 내역을 원본 JSON에 저장하고 종료합니다.
- **1차 추천 API 호출 실패**(인증/쿼터/네트워크) → 같은 요청을 반복해도 결과가 같을 가능성이 높으므로 재시도하지 않고 종료합니다.
- **최종 리포트 LLM 실패 또는 필수 섹션 누락** → 수집한 데이터로 템플릿 리포트를 만들어 대체합니다.

## 캐시 (보너스)

같은 `--date`(및 같은 `--cities`/`--places`/`--mock` 옵션)로 다시 실행하면 저장된 `*_raw.json`을 재사용해 **API를 호출하지 않고** Markdown/HTML을 다시 만듭니다.
이전 실행에 오류(0건 제외)가 있었다면 키를 고친 뒤 재실행하는 상황일 수 있으므로 캐시를 쓰지 않습니다. 강제로 새로 만들려면 `--no-cache`.

## API 키 유출 방지 주의사항

- 키는 **코드·README·결과 파일에 절대 직접 쓰지 않습니다.** `.env` 또는 환경변수에서만 읽습니다.
- `.env`는 `.gitignore`에 들어 있습니다. 커밋 전 `git status`로 `.env`가 목록에 없는지 확인하세요. 공유용으로는 값이 빈 `.env.example`만 올립니다.
- 키는 URL 쿼리(`?key=...`)가 아니라 **HTTP 헤더**로 보냅니다. URL은 로그·프록시·브라우저 기록에 남기 쉽기 때문입니다.
- 오류 메시지는 저장/출력 전에 키 값과 키 형식 문자열(`sk-...`, `AIza...`, `KakaoAK ...`)을 `***`로 가립니다.
- 실수로 키가 공개되었다면 **즉시 해당 콘솔에서 키를 폐기(재발급)** 하세요. 커밋 기록에서 지우는 것만으로는 부족합니다.
- 유료 API(OpenAI)는 콘솔에서 사용 한도(Usage limit)를 걸어 두면 사고 시 피해를 줄일 수 있습니다.

## 테스트

API 키 없이 실행됩니다. 가짜 HTTP 응답으로 401/429/네트워크 오류/0건/JSON 재시도/캐시/키 미노출 등을 검증합니다.

```bash
python -m unittest discover -s tests -v
```

## 학습 정리

- **REST 요청/응답 구조**: 요청 = 메서드 + URL + 헤더(인증 키, Content-Type) + (본문). 응답 = 상태 코드 + 헤더 + 본문(JSON).
- **GET vs POST**: 맛집 검색은 서버 데이터를 *조회*만 하므로 `GET` + 쿼리스트링(`?query=제주 맛집`). LLM 호출은 긴 프롬프트를 *보내서 처리시키므로* `POST` + JSON 본문.
- **LLM 출력 구조화**: 프롬프트로 스키마를 지정하고, JSON 모드(`response_format` / `responseMimeType`)를 켜고, 그래도 코드블록·설명이 섞일 수 있으니 `extract_json()`으로 복구 후 필수 키/타입을 검증한 다음에야 `recommended_city`를 지도 검색어로 씁니다.
- **오류 대응 원칙**: 원인별로 분류해서 기록하고, 부분 실패(맛집)는 우아하게 degrade, 필수 단계(추천) 실패는 명확히 종료, 재시도는 횟수를 제한.
- **키를 환경변수로 관리하는 이유**: 공유·커밋 시 유출 방지, 키를 바꿔도 코드 수정 불필요, 과금 사고 예방.
