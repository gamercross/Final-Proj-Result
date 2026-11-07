"""환경변수/.env에서 설정과 API 키를 읽는다. 키는 절대 코드에 쓰지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .errors import register_secret

SUPPORTED_LLM = ("openai", "gemini")


@dataclass
class Settings:
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    gemini_api_key: str | None
    gemini_model: str
    kakao_rest_api_key: str | None
    timeout: float

    @property
    def llm_key_name(self) -> str:
        return "OPENAI_API_KEY" if self.llm_provider == "openai" else "GEMINI_API_KEY"

    @property
    def llm_api_key(self) -> str | None:
        return self.openai_api_key if self.llm_provider == "openai" else self.gemini_api_key

    @property
    def llm_model(self) -> str:
        return self.openai_model if self.llm_provider == "openai" else self.gemini_model


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_settings() -> Settings:
    # 현재 폴더의 .env를 읽는다. 이미 설정된 환경변수가 있으면 그쪽이 우선.
    load_dotenv(override=False)

    provider = (_env("LLM_PROVIDER") or "openai").lower()
    if provider not in SUPPORTED_LLM:
        raise SystemExit(
            f"[설정 오류] LLM_PROVIDER='{provider}' 는 지원하지 않습니다. "
            f"{' / '.join(SUPPORTED_LLM)} 중 하나로 설정하세요."
        )

    try:
        timeout = float(_env("HTTP_TIMEOUT") or 30)
    except ValueError:
        timeout = 30.0

    settings = Settings(
        llm_provider=provider,
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL") or "gpt-4o-mini",
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL") or "gemini-2.5-flash",
        kakao_rest_api_key=_env("KAKAO_REST_API_KEY"),
        timeout=timeout,
    )
    for key in (settings.openai_api_key, settings.gemini_api_key, settings.kakao_rest_api_key):
        register_secret(key)
    return settings


def missing_keys(settings: Settings, *, need_llm: bool, need_places: bool) -> list[str]:
    missing = []
    if need_llm and not settings.llm_api_key:
        missing.append(settings.llm_key_name)
    if need_places and not settings.kakao_rest_api_key:
        missing.append("KAKAO_REST_API_KEY")
    return missing


def setup_guide(missing: list[str]) -> str:
    lines = [
        "[설정 오류] 다음 API 키가 설정되지 않았습니다: " + ", ".join(missing),
        "",
        "설정 방법 (택1):",
        "  1) .env 파일 사용 (권장)",
        "     cp .env.example .env   # 그 다음 .env 파일을 열어 값을 채우세요",
        "",
        "  2) 환경변수로 직접 설정 (현재 터미널 세션에만 적용)",
    ]
    for name in missing:
        lines.append(f'     macOS/Linux : export {name}="YOUR_KEY"')
        lines.append(f'     PowerShell  : $env:{name}="YOUR_KEY"')
    lines += [
        "",
        "키 발급 방법은 README.md의 'API 키 설정' 항목을 참고하세요.",
        "키 없이 흐름만 확인하려면 --mock 옵션으로 실행하세요.",
    ]
    return "\n".join(lines)
