# FINN — instructions for any coding agent working in this repo

FINN is a mobile-first investor agent built for the ENAM build challenge (deadline 15 Nov 2026).
Three parts: **Push** (the "Today" brief of exchange filings), **Pull** (Research, centred on the
Promise Ledger: what management guided vs what it delivered), **Network** (People: who to call,
second-degree paths, dossiers). Live: web on Vercel, API on Render, data in Neon Postgres.

**Entry point: [`continuing_prompt.md`](continuing_prompt.md).** Read this file, then `PROGRESS.md` (latest checkpoint at the bottom), `docs/STATUS.md`
(what is done / partial / missing, with screenshots) and the tail of `docs/DECISIONS.md` before
changing anything.** `docs/HANDOFF.md` has the prompt to resume work and the ordered next steps.

## How to work here without breaking what exists

1. **The engine is frozen** (owner, 13 Nov). No new companies, data sources, ledger/scoring rules
   or research sections. The one allowed engine change: Trajectory extended to multi-year from
   NSE's structured (XBRL) results. Remaining time goes to the frontend and the submission docs.
2. **Additive changes only.** Don't rename, move, reformat or "clean up" working files. Don't
   rewrite a component to add a feature: add a component or a prop. Don't change a function's
   behaviour unless the task is that change; if you must, run the tests that cover it.
3. **Read before you edit**, and read the tests next to the code (`api/tests/`, `web/lib/*.test.ts`).
   Every scoring/extraction rule here was added to fix a specific, documented failure
   (DECISIONS.md); removing one reintroduces that failure.
4. **Correct on real data or hidden.** Never invent data. Models extract; code computes. A model-
   written line must be grounded in the filing (`severity.grounded`). Missing evidence is shown
   as "not scored", "years not stated", "Not read yet", never filled in.
5. **Log every decision** in `docs/DECISIONS.md` (dated section, what and why) and keep
   `docs/STATUS.md` honest. Update `PROGRESS.md` at each stopping point.
6. **Stop points**: the owner asks for a stop + phone-width (390 px) screenshot after each
   numbered item. Use `node scripts/phone_shot.mjs <url> <out.png> '<steps json>' [dark|light]`.
7. Commit with a clear message and push only when checks pass. Never commit secrets.

## Owner's hard rules (never break)
- Zero spend: free tiers only; never sign up for anything needing a card.
- NSE access: one request at a time, ≥ 1.2 s apart, cache everything, never re-fetch a document,
  demo companies and on-demand tickers only, never re-host PDFs (store text, link the original),
  credit NSE in the UI. **If `data/cache/SOURCE_REFUSED.json` exists: stop, tell the owner, do
  not delete it.** NSE from the laptop only on the owner's phone hotspot (campus Wi-Fi is refused);
  GitHub runners are accepted by NSE.
- Company IR sites: robots.txt respected, permanent `IR_REFUSED_<host>.json` stop on refusal.
- Never print API keys or connection strings. Ask before destructive actions.

## Map of the code
- `api/finn/` (Python 3.11, FastAPI, psycopg, Postgres):
  - `api/main.py` read-only API: serves materialised `views(key, body)`; `/api/research/jobs` writes jobs.
  - `cli.py` `finn` commands: `push [--offline] [--no-llm]`, `research SYMS [--offline]`, `network`,
    `ingest`, `worker [--job N]`, `export-snapshot`, `import-transcripts`.
  - `push/` Today brief: `classify_rules.py` (category rules), `severity.py` (text-based scoring of
    event filings, empty-summary and grounding checks), `pipeline.py` (stages: rules → severity →
    fact lines → management lines → label lines → grounding), `brief.py` (ranking/tiers), `alerts.py`.
  - `pull/` Research: `guidance.py` (extraction), `research.py` (chains, verdicts, groups, ledger),
    `reported.py` (company-reported actuals), `business.py` (segments, "what it does"), `eval_guidance.py`.
  - `network/` contacts, careers (`service.clean_public_careers`), paths, dossiers; synthetic data in `synthetic.py`.
  - `llm/` router (tiers BULK/EXTRACT/REASON, Gemini → Groq → local), cache, cost ledger.
  - `sources/` NSE polite client (`http.py`, refusal marker), IR fetcher, PDF text.
  - `jobs.py` live-research queue (laptop worker or GitHub Actions `research.yml`).
  - `migrations/` SQL, applied by `db.migrate`.
- `web/` (Next.js 16, React 19, Tailwind 4 — read `web/AGENTS.md`: this Next.js has breaking changes):
  `components/` Today, ResultsCard, WhySheet, Network (sheets, paths), Research, Ledger
  (scoreboard, chain timelines, Who can help), ResearchJob, People, Alerts, Cost; `lib/` api
  (live → snapshot fallback), types, alerts (mirrors Python evaluator), whoKnows.
  `public/snapshot/*.json` = bundled fallback (regenerate with `finn export-snapshot`).
- `scripts/` `neon_http.py` (HTTPS mirror/write-back for Neon), `phone_shot.mjs`,
  `ranking_snapshot.py`, `fetch_annual_reports.py`.
- `data/` `portfolio.json`, `research_set.json` (hero CREDITACC), `eval/` (gold sets, labelled filings).
- `docs/` SPEC, ARCHITECTURE (+ svg), STATUS, DECISIONS, PHASES, evals, WRITEUP, screens/.

## Environments
- Campus Wi-Fi blocks Postgres 5432 and NSE. Work against the local Docker copy
  `postgresql://finn:finn@localhost:5432/finn_mirror` (container `enam-afe-db-1`) and write back
  with `python scripts/neon_http.py push-views <prefix>` / `push-filing-class` / `push-llm`
  (allowlisted: pipeline-owned data only; never the live app's tables such as `research_jobs`).
- On the hotspot, the Neon URL in `.env` works directly; refresh the local copy with pg_dump (see PROGRESS.md).
- Local servers: API `cd api && DATABASE_URL=…finn_mirror CORS_ORIGINS=http://localhost:3006 .venv/Scripts/python -m uvicorn finn.api.main:app --port 8000`;
  web `cd web && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run build && npx next start -p 3006`
  (after a rebuild, restart the server: a server left running on a replaced build hangs on "Loading…").

## Checks (run before every commit): `bash scripts/verify.sh`
`cd api && .venv/Scripts/ruff check finn tests && .venv/Scripts/mypy finn && .venv/Scripts/python -m pytest -q`
`cd web && npx eslint . && npx tsc --noEmit && npm test && npm run build`
(85 API tests and 14 web tests passed at the last checkpoint.)

## Gotchas
- Bash heredocs here turn `\b` into a backspace byte in Python/regex files. Use the Edit/Write
  tools for regex-heavy code, or afterwards replace `chr(8)` with `\\b`.
- Windows + OneDrive; git normalises CRLF→LF (`.gitattributes`). Line-ending-only diffs are not changes.
- Headless Chrome needs CDP device emulation for 390 px (the screenshot script does this).
- Next.js 16: no synchronous setState in effects; no `Date.now()` during render.
