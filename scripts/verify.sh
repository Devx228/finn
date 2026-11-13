#!/usr/bin/env bash
# One command to prove nothing regressed: run before you change anything and after every change.
# Exits non-zero on the first failure. Run from the repo root:  bash scripts/verify.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=api/.venv/Scripts/python
[ -x "$PY" ] || PY=api/.venv/bin/python

echo "== API: lint, types, tests"
( cd api && "../$PY" -m ruff check finn tests && "../$PY" -m mypy finn && "../$PY" -m pytest -q )

echo "== Web: lint, types, tests, build"
( cd web && npx eslint . && npx next typegen >/dev/null && npx tsc --noEmit && npm test --silent && npm run build >/dev/null )

echo "== Secrets: none tracked"
if git ls-files | grep -E '(^|/)\.env($|\.)' | grep -v '\.env\.example$'; then
  echo "a .env file is tracked"; exit 1
fi
if git grep -nE '(AIza[0-9A-Za-z_-]{30,}|gsk_[0-9A-Za-z]{20,}|ghp_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,}|npg_[0-9A-Za-z]{10,})' -- . ':!*.lock' ; then
  echo "a key-like string is tracked"; exit 1
fi

echo "OK: all checks green"
