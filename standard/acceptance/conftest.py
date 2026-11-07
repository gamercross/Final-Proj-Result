"""수용 시험 준비 — 어느 구현이든 폴더만 주면 같은 시험을 돈다.

    IMPL_DIR=<구현 폴더> IMPL_PYTHON=<그 구현의 패키지가 깔린 python> python -m pytest standard/acceptance

구현은 새 빈 폴더(작업 폴더)에서 `python <IMPL_DIR>/travel_planner.py -date …`로 돌린다.
API 주소는 가짜 서버로, 키는 가짜 값으로 준다. 진짜 키 · 진짜 서버는 쓰지 않는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from fake_server import FakeServer

OPENAI_KEY = "sk-fake-OPENAI-0123456789abcdef"  # 시험용 가짜 값 — secret-check: allow
KAKAO_KEY = "fakekakao0123456789abcdefKAKAO"  # 시험용 가짜 값 — secret-check: allow
DATE = "2026-11-21"


def _impl() -> Path:
    d = os.environ.get("IMPL_DIR")
    if not d:
        pytest.exit("IMPL_DIR(구현 폴더)를 주세요", returncode=2)
    p = Path(d).resolve()
    if not (p / "travel_planner.py").is_file():
        pytest.exit(f"{p}/travel_planner.py가 없습니다", returncode=2)
    return p


@pytest.fixture(scope="session")
def impl() -> Path:
    return _impl()


@pytest.fixture(scope="session")
def server():
    with FakeServer() as s:
        yield s


@pytest.fixture
def run(impl, server, tmp_path):
    """구현을 한 번 돌린다. 돌려준 것: (끝 코드, 화면 글, 작업 폴더)"""
    server.reset()

    def _run(*args, env_drop=(), env_set=None, date=DATE):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("OPENAI_", "KAKAO_", "GEMINI_", "NAVER_", "LLM_"))}
        env.update({
            "OPENAI_API_KEY": OPENAI_KEY, "KAKAO_REST_API_KEY": KAKAO_KEY,
            "OPENAI_BASE_URL": server.url + "/v1", "KAKAO_BASE_URL": server.url,
            "OPENAI_MODEL": "gpt-4o-mini", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1",
        })
        env.update(env_set or {})
        for k in env_drop:
            env.pop(k, None)
        argv = [os.environ.get("IMPL_PYTHON", sys.executable), str(impl / "travel_planner.py"), *args]
        if date is not None:
            argv += ["-date", date]
        p = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90)
        return p.returncode, p.stdout + p.stderr, tmp_path

    return _run
