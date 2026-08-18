#!/usr/bin/env bash
# Repo gate. Must pass on a clean tree before any autonomous loop runs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -x .venv/bin/python ]; then
  echo "check.sh: missing .venv — create it with:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r cookie-banner-auditor/scripts/requirements.txt" >&2
  exit 2
fi

echo "== cookie-banner-auditor smoke tests =="
cd cookie-banner-auditor
"$REPO_ROOT/.venv/bin/python" scripts/tests/smoke_test.py
