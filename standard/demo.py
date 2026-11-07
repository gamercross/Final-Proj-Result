"""가짜 서버로 구현을 한 번 돌려 results/를 만든다 — 구현마다 같은 데이터로 화면을 견주려고.

    python standard/demo.py <구현 폴더> <결과를 둘 폴더> [그 구현의 python]
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "acceptance"))
from fake_server import FakeServer  # noqa: E402

impl, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
py = sys.argv[3] if len(sys.argv) > 3 else sys.executable
with FakeServer() as s, tempfile.TemporaryDirectory() as cwd:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENAI_", "KAKAO_"))}
    env.update(OPENAI_API_KEY="sk-demo", KAKAO_REST_API_KEY="demo", OPENAI_BASE_URL=s.url + "/v1", KAKAO_BASE_URL=s.url)
    p = subprocess.run([py, str(impl / "travel_planner.py"), "-date", "2026-11-21"], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    print(p.stdout + p.stderr)
    out.mkdir(parents=True, exist_ok=True)
    for f in (Path(cwd) / "results").glob("*"):
        shutil.copy(f, out / f.name)
    (out / "run-log.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
