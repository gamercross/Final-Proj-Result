"""공통 HTTP 호출 + 오류 분류 + 오류 목록 관리.

외부 API 호출에서 자주 만나는 오류를 아래처럼 분류한다.
- AUTH_ERROR    : 401/403 (키가 틀렸거나, 권한/서비스 활성화가 안 됨)
- QUOTA_ERROR   : 429 (호출 한도 초과, 잔액 부족)
- SERVER_ERROR  : 5xx (제공자 쪽 장애)
- HTTP_ERROR    : 그 밖의 4xx (요청 형식 오류 등)
- NETWORK_ERROR : 타임아웃, DNS 실패, 연결 끊김
- PARSE_ERROR   : 응답이 JSON이 아니거나, 기대한 구조가 아님
- VALIDATION_ERROR : JSON은 맞지만 필수 키/타입이 맞지 않음
- EMPTY_RESULT  : 정상 응답이지만 결과가 0건
"""

from __future__ import annotations

import re
from typing import Any

import requests

AUTH_ERROR = "AUTH_ERROR"
QUOTA_ERROR = "QUOTA_ERROR"
SERVER_ERROR = "SERVER_ERROR"
HTTP_ERROR = "HTTP_ERROR"
NETWORK_ERROR = "NETWORK_ERROR"
PARSE_ERROR = "PARSE_ERROR"
VALIDATION_ERROR = "VALIDATION_ERROR"
EMPTY_RESULT = "EMPTY_RESULT"

# 로그/결과 파일에 키가 새지 않도록, 등록된 비밀값은 출력 전에 가린다.
_SECRETS: set[str] = set()
_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-*]{6,}"),  # OpenAI 형식 키
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google API 키 형식
    re.compile(r"KakaoAK\s+\S+"),
]


def register_secret(value: str | None) -> None:
    if value and len(value) >= 6:
        _SECRETS.add(value)


def redact(text: str) -> str:
    for secret in _SECRETS:
        text = text.replace(secret, "***")
    for pattern in _KEY_PATTERNS:
        text = pattern.sub("***", text)
    return text


class APIError(Exception):
    """외부 API 호출 실패. type은 위의 분류 상수 중 하나."""

    def __init__(self, type_: str, message: str, status: int | None = None):
        self.type = type_
        self.message = redact(message)
        self.status = status
        super().__init__(f"{type_}: {self.message}")


def _error_detail(resp: requests.Response) -> str:
    """응답 본문에서 사람이 읽을 만한 오류 메시지를 짧게 뽑는다."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:200]
        if body.get("message"):
            return str(body["message"])[:200]
    return str(body)[:200]


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    """HTTP 요청을 보내고 JSON 응답을 돌려준다. 실패하면 APIError를 던진다."""
    try:
        resp = requests.request(
            method, url, headers=headers, params=params, json=json_body, timeout=timeout
        )
    except requests.Timeout:
        raise APIError(NETWORK_ERROR, f"요청 시간 초과({timeout:.0f}초)")
    except requests.ConnectionError as exc:
        raise APIError(NETWORK_ERROR, f"연결 실패: {type(exc).__name__}")
    except requests.RequestException as exc:
        raise APIError(NETWORK_ERROR, f"요청 실패: {type(exc).__name__}")

    status = resp.status_code
    if status in (401, 403):
        raise APIError(AUTH_ERROR, f"HTTP {status}: {_error_detail(resp)}", status)
    if status == 429:
        raise APIError(QUOTA_ERROR, f"HTTP 429: {_error_detail(resp)}", status)
    if status >= 500:
        raise APIError(SERVER_ERROR, f"HTTP {status}: {_error_detail(resp)}", status)
    if status >= 400:
        raise APIError(HTTP_ERROR, f"HTTP {status}: {_error_detail(resp)}", status)

    try:
        return resp.json()
    except ValueError:
        raise APIError(PARSE_ERROR, "응답 본문이 JSON이 아닙니다", status)


class ErrorLog:
    """실행 중 발생한 오류를 모아 두었다가 원본 JSON/리포트에 남긴다."""

    def __init__(self, items: list[dict[str, str]] | None = None):
        self.items: list[dict[str, str]] = list(items or [])

    def add(self, step: str, type_: str, message: str) -> None:
        self.items.append({"step": step, "type": type_, "message": redact(message)})

    def to_list(self) -> list[dict[str, str]]:
        return list(self.items)

    def __len__(self) -> int:
        return len(self.items)
