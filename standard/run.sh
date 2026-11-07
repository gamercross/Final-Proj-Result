#!/usr/bin/env bash
# 구현 폴더 하나를 기준 v1 수용 시험으로 돌린다 — 그 구현의 패키지를 새 가상환경에 깔고(폴더는 건드리지 않음) 시험 24개.
#   bash standard/run.sh <구현 폴더>
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
impl=$(cd "${1:?구현 폴더를 주세요}" && pwd)
venv=$(mktemp -d)/venv
python3 -m venv "$venv"
"$venv/bin/pip" -q install pytest
[ -s "$impl/requirements.txt" ] && "$venv/bin/pip" -q install -r "$impl/requirements.txt"
cd "$here/acceptance"
IMPL_DIR="$impl" IMPL_PYTHON="$venv/bin/python" "$venv/bin/python" -m pytest -q -p no:cacheprovider "${@:2}"
