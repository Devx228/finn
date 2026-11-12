# FINN — progress (resumable)

Kept current with every commit so any agent or model can pick up the work.
Authority order: `docs/brief.pdf` > owner's decisions in `docs/DECISIONS.md` > `docs/SPEC.md`.

## Rules that override the spec
- **Zero spend.** Never sign up for anything that asks for a card; stop and tell the owner.
- Local-first; every external service swapped by env vars only (`.env.example`).
- One phase at a time; show the gate with real output; stop for owner review.
- Log every non-trivial decision in `docs/DECISIONS.md`. Never commit secrets.

## Status
- **Phase 0a (local skeleton): gate passed in emulation (2026-11-12); waiting for the owner's
  real-phone check and review.** Evidence: emulated 390×844 iPhone, API up → "Live" badge;
  API stopped → "Snapshot" badge; scrollWidth 390 both times. API 5 tests, web 5 tests,
  ruff/mypy/eslint/tsc clean, `next build` ok, API Docker image runs against local Postgres.
- Phase 0b (deploy): waiting on accounts (GitHub repo, Neon, Vercel, Render). Hugging Face
  Spaces, Koyeb and Cerebras are ruled out (paid plan or card) — see DECISIONS.md.

## How to run locally
```bash
docker compose up -d --wait                        # Postgres 16 on :5432
cp .env.example .env                               # once
cd api && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/finn migrate && .venv/Scripts/finn seed-placeholder
.venv/Scripts/uvicorn finn.api.main:app --host 0.0.0.0 --port 8000
cd ../web && npm install && npm run dev -- -H 0.0.0.0 # http://localhost:3000
```
Checks: `cd api && .venv/Scripts/ruff check . && .venv/Scripts/mypy finn && .venv/Scripts/pytest -q`;
`cd web && npm run lint && npx tsc --noEmit && npm test && npm run build`.

Phone over Wi-Fi: `NEXT_PUBLIC_API_BASE` is baked in at build time, so build with the LAN IP:
`NEXT_PUBLIC_API_BASE=http://<lan-ip>:8000 npm run build && npx next start -H 0.0.0.0 -p 3000`,
and start the API with `CORS_ORIGINS=http://<lan-ip>:3000`. Refresh the snapshot with
`api/.venv/Scripts/finn export-snapshot`.

## Next steps
1. Owner reviews Gate 0a → creates accounts (GitHub repo, Neon, Vercel, Render) → Phase 0b.
2. Phase 1 (data plumbing) only after the owner's go-ahead.
