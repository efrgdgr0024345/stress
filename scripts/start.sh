#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [[ ! -f dist/index.html ]]; then
  printf 'The website has not been built. Run ./scripts/setup.sh first.\n' >&2
  exit 1
fi
runtime_python="${CAESAR_PYTHON:-$project_root/.venv/bin/python}"
if [[ ! -x "$runtime_python" ]]; then
  runtime_python="$(command -v python)"
fi
exec "$runtime_python" -m uvicorn services.api.main:app --host "${BIND_HOST:-127.0.0.1}" --port "${PORT:-3000}"
