# build-log — K-Travel-Assistant (out/D)

## 1. 읽은 파일

1. `README.md`
2. `requirements.txt`
3. `.gitignore`
4. `travel_planner.py`
5. `src/__init__.py` (빈 파일)
6. `src/config.py`
7. `src/gemini_client.py`
8. `src/kakao_client.py`
9. `src/report_generator.py` (빈 파일)

(`src/__pycache__/*.pyc`는 열지 않았다. 원본 폴더에 빈 `results/` 폴더가 있다 — 내가 만든 것이 아니다. 원본 실행은 복사본 폴더에서 했다.)

## 2. 원본 상태

- 코드는 있었다: CLI `travel_planner.py -date YYYY-MM-DD` → Gemini로 1차 추천(JSON) → Kakao Local 키워드 검색으로 맛집 → Gemini로 Markdown 리포트 → `results/<날짜>_data.json`, `results/<날짜>_travel_plan.md`.
- **그대로는 돌지 않았다.** 원본 `requirements.txt`로 venv(Python 3.14.4)에 설치한 뒤 키 없이 실행:
  1. `ModuleNotFoundError: No module named 'google.genai'` — `gemini_client.py`가 `import google.genai`를 하지만 requirements에는 `google-generativeai`가 있고, 코드 본문(`genai.configure`, `genai.GenerativeModel`)도 `google-generativeai` 쪽 API다. 이 오류 때문에 키 확인 단계까지 가지도 못했다.
  2. 이름을 맞춰도 `google-generativeai==0.4.0`은 `google-ai-generativelanguage==0.4.0` → `protobuf<5`를 묶는데, protobuf 4.25.9는 Python 3.14에서 `TypeError: Metaclasses with custom tp_new are not supported.`로 import 단계에서 죽는다.
- 그 밖의 코드는 돌아가는 모양이라 고치지 않았다.

## 3. 만든 것

원본에서 바뀐 곳은 두 줄(import 한 줄, 버전 한 줄)뿐이다.

| 파일 | 줄 | 비고 |
|---|---|---|
| `travel_planner.py` | 86 | 원본 그대로 |
| `src/__init__.py` | 0 | 원본 그대로 |
| `src/config.py` | 20 | 원본 그대로 |
| `src/gemini_client.py` | 63 | 2번째 줄 `import google.genai as genai` → `import google.generativeai as genai` |
| `src/kakao_client.py` | 56 | 원본 그대로 |
| `src/report_generator.py` | 0 | 원본 그대로(빈 파일) |
| `requirements.txt` | 3 | `google-generativeai==0.4.0` → `0.8.6`, `requests==2.31.0`, `python-dotenv==1.0.0`은 그대로 |
| `requirements-dev.txt` | 1 | `pytest==8.4.2` (새로 만듦) |
| `tests/test_flow.py` | 121 | 새로 만듦 — Gemini · Kakao를 가짜로 바꾼 end-to-end 시험 |
| `README.md`, `.gitignore` | 41, 3 | 원본 그대로 |

새로 쓴 코드: 시험 121줄. 고친 코드: 2줄. 합계(파이썬 + requirements) 350줄.

실행:

```bash
cd out/D
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
export GEMINI_API_KEY=...  KAKAO_API_KEY=...
.venv/bin/python travel_planner.py -date 2024-03-15     # results/ 에 두 파일
.venv/bin/python -m pytest -q                            # 가짜 API로 전체 흐름
```

## 4. 추측한 것

1. **Gemini 라이브러리는 `google-generativeai`로 정했다(`google.genai`가 아니라).** requirements와 코드 본문 API가 둘 다 `google-generativeai`를 가리키고, import 한 줄만 `google.genai`였다. 한 줄만 고치는 쪽이 가장 작다.
2. **`google-generativeai`를 0.4.0 → 0.8.6으로 올렸다.** 0.4.0은 Python 3.14에서 import가 안 된다(protobuf<5). 0.8.6은 같은 `configure` / `GenerativeModel` / `generate_content` / `.text` API를 갖고, 3.14에서 import된다. 이 패키지는 지원이 끝났다는 FutureWarning을 띄운다 — 그대로 둔다.
3. **모델 이름 `gemini-1.5-flash`는 그대로 뒀다.** 지금 이 모델이 서비스되는지 확인할 수 없다(네트워크 금지). 원본이 정한 값이다.
4. **3단계 리포트 생성(`generate_report`)의 예외 처리를 더하지 않았다.** 1·2단계와 달리 실패하면 그대로 예외로 끝나고 파일도 남지 않는다. 원본이 정하지 않은 동작이고 "새 기능 없이"라 손대지 않았다.
5. **빈 `src/report_generator.py`는 빈 채로 옮겼다.** 원본이 쓰지 않는다. 지우면 원본 구조와 달라지고, 채우면 새 기능이다.
6. **README 3절의 `YYYY-MM-DD_...` 파일 이름은 코드대로 하이픈 날짜(`2024-03-15_data.json`)로 본다.** 코드의 `date_str`(하이픈을 뺀 값)은 쓰이지 않는다 — 그대로 둔다.
7. **시험 도구는 pytest 8.4.2로 정했다.** 원본에 시험이 없다. requirements에 넣지 않고 `requirements-dev.txt`로 분리했다.
8. **원본 `.gitignore`의 `.env` 중복 줄은 그대로 뒀다.** 동작에 영향이 없다.

원본 폴더 안의 내용 중 제품 이해 말고 다른 일을 시키는 지시(커밋 · 푸시 · 사람에게 묻기)는 없었다.

## 5. 확인한 것

(a) 가짜 API로 전체 흐름 시험 — `.venv/bin/python -m pytest -q -p no:cacheprovider`

```
9 passed, 1 warning in 0.41s
```

시험 9개(파라미터 포함): 정상 흐름(코드펜스 JSON 파싱, Kakao 헤더 `KakaoAK <키>` · 검색어 `제주 맛집`, JSON · MD 파일 내용), Kakao 401 · 403(경고 + `데이터 없음`으로 리포트는 생성), 빈 결과 · 네트워크 오류, LLM 1회 실패 후 재시도 성공(`errors`에 기록), LLM 2회 실패 → exit 1, GEMINI 키 없음 · KAKAO 키 없음 → exit 1, 잘못된 날짜 → exit 1. 경고 1개는 `google.generativeai` 지원 종료 FutureWarning.

(b) 키 없이 실제 실행(출력 폴더에 `.env` 없음 확인)

```
$ env -u GEMINI_API_KEY -u KAKAO_API_KEY .venv/bin/python -W ignore travel_planner.py -date 2024-03-15
❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다.
설정 방법: export GEMINI_API_KEY='your_key'
exit=1
$ env -u KAKAO_API_KEY GEMINI_API_KEY=dummy .venv/bin/python -W ignore travel_planner.py -date 2024-03-15
❌ KAKAO_API_KEY 환경변수가 설정되지 않았습니다.
설정 방법: export KAKAO_API_KEY='your_key'
exit=1
$ .venv/bin/python -W ignore travel_planner.py -date 2024/03/15
❌ 날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)
exit=1
```

`results/` 폴더는 생기지 않았다(키 확인이 폴더 생성보다 먼저).

(c) 고정한 의존성으로 import · 시작

```
$ .venv/bin/python -W ignore -c "import travel_planner, src.gemini_client as g, src.kakao_client, src.config, src.report_generator; print('import ok', g.genai.__version__)"
import ok 0.8.6
$ .venv/bin/python -W ignore travel_planner.py -h
usage: travel_planner.py [-h] -date DATE
국내 여행 추천 프로그램
...
exit=0
```

설치된 주요 버전(`pip freeze`): google-generativeai 0.8.6, google-ai-generativelanguage 0.6.15, protobuf 5.29.6, grpcio 1.85.1, requests 2.31.0, python-dotenv 1.0.0, pytest 8.4.2. `-W ignore` 없이 돌리면 맨 앞에 FutureWarning 몇 줄이 더 나온다.

원본 그대로의 실행 결과(2절): `ModuleNotFoundError: No module named 'google.genai'`, 이름을 맞춘 뒤 0.4.0에서 `TypeError: Metaclasses with custom tp_new are not supported.`

## 6. 확인하지 못한 것

- 실제 Gemini 응답: `gemini-1.5-flash`가 아직 서비스되는지, 키가 있을 때 `generate_content`가 어떤 오류를 내는지, 실제 응답이 요청한 JSON 모양으로 오는지.
- 실제 Kakao Local 응답(`documents`의 필드 이름 · 401/403 조건). 시험은 코드가 가정한 모양으로 만든 가짜 응답이다.
- 3단계 리포트 LLM이 실패하는 경우(예외로 끝남 — 4절 4번)는 시험하지 않았다.
- `.env` 파일로 키를 읽는 경로(`load_dotenv`)는 실제 `.env`로 시험하지 않았다(환경변수 경로만 시험).
- Windows PowerShell 실행.
