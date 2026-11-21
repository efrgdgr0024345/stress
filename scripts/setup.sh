#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python -m venv .venv
PIP_CACHE_DIR="$project_root/.cache/pip" .venv/bin/python -m pip install -r requirements-dev.txt
npm ci --cache "$project_root/.cache/npm" --no-audit --no-fund
npm run build
.venv/bin/python -m unittest discover -s tests -v
printf '\nSetup verified. Start the website with ./scripts/start.sh\n'
