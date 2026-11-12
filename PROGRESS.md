# FINN — progress & handover (read this first)

Kept current with every commit so any agent or model can resume without the chat history.

**Authority order:** `docs/brief.pdf` (the challenge) > owner decisions in `docs/DECISIONS.md`
> `docs/SPEC.md` (build spec, edited inline where the owner changed it). Gate evidence for each
phase is in `docs/PHASES.md`. Deadline: **15 Nov 2026**.

## Hard rules (owner)
- **Zero spend.** Never sign up for anything that asks for a card/billing; stop and tell the owner.
- **NSE access rules** (DECISIONS 2026-11-12): never bypass a block/bot check/rate limit; one
  request at a time ≥ 1 s apart (enforced in `api/finn/sources/http.py`); cache everything, never
  refetch a document; fetch only demo companies + on-demand tickers; never re-host PDFs (store
  text, link to NSE); credit NSE in the UI. If `data/cache/SOURCE_REFUSED.json` exists, NSE
  refused us: STOP and tell the owner; do not delete it yourself.
- Never invent data. Models extract and explain; code computes. No claim without a source.
- Work phase by phase (spec §16); show each gate with real output in docs/PHASES.md; log
  decisions in DECISIONS.md. Owner said (12 Nov) to continue while away and log every phase.
- Don't rerun test suites/rebuilds after trivial changes; run tests at gates and before logic
  commits. Ask before destructive actions (DB drops, volume deletes).
- Never commit secrets. `.env` holds the Neon `DATABASE_URL` (owner pasted it there).

## Where things are
| What | Where |
|---|---|
| Web (Vercel Hobby, root `web/`) | https://finn-tawny-nine.vercel.app — env `NEXT_PUBLIC_API_BASE` |
| API (Render free, Docker, `render.yaml`) | https://finn-api-mxni.onrender.com — env `DATABASE_URL`, `CORS_ORIGINS` |
| DB | Neon free, Postgres 18 (Singapore). Local dev: `docker compose up -d --wait` (PG 18) |
| Repo | github.com/Devx228/finn (**private**; make public in Phase 6 after a secret scan) |
| Redeploy | push to `main` → Render + Vercel auto-deploy |
| NSE from Render | **403 — server never calls NSE.** GitHub runners and the laptop can. |

## Status
- Phase 0a ✅ (owner's phone) · Phase 0b ✅ (public URLs) — see docs/PHASES.md.
- **Phase 1 ✅ (2026-11-12)** — evidence in docs/PHASES.md. DB (Neon) holds 22 demo companies:
  prices, 1,199 filings (130 with PDF text), transcript + AR links, 540 XBRL filings / 72,803 facts,
  `coverage:<SYM>` views. Portfolio/research set in `data/portfolio.json`, `data/research_set.json`.
- **Phase 2 ✅ (2026-11-13)** — evidence in docs/PHASES.md; eval in docs/evals.md. Run the push
  side with `finn push` (rules → thin texts → qwen2.5:7b → results cards → briefs), then
  `finn export-snapshot` and push to deploy. Replay deep link: `/?w=7d&as_of=2026-10-31`.
- **Phase 3 ✅ (2026-11-13)** — network in the brief (bio from filing, second-degree paths, "you
  overlapped" with the investor's own CV, who-to-call with insider flag, worth-asking questions),
  People tab (new faces, reasons to reconnect, who-to-call by company, expertise map, coverage),
  alerts (volume ×, ±%, vs NIFTY, categories; client-side with "would have fired N times").
  `finn network [--seed]` materialises network views; `finn push` now also does network + alerts.
- **Phase 4 partial** — `finn research SYM[,SYM]` builds `research:<SYM>` (+ `research:index`):
  XBRL trajectory, guidance tracker from last 4 calls, verdicts, bull/bear, who-to-call. Built for
  INFY, KAYNES, CREDITACC, TRENT, PERSISTENT, DEEPAKNTR, HDFCBANK. Research screen done.
  Gate shortfall logged in docs/PHASES.md.
- **Promise Ledger rework (2026-11-13)** — cc guidance resolved against company-reported cc growth,
  filing-checked capex/loan growth/credit cost/ROA/ROE, chains end to end, ledger counts, hosted
  extraction tier `EXTRACT` (eval in docs/evals.md). Scope status table: docs/STATUS.md.
- **BLOCKERS (owner):** (1) `data/cache/SOURCE_REFUSED.json` — NSE 403'd the laptop on 13 Nov; no NSE
  calls until the owner decides. (2) This Wi-Fi resets Postgres on 5432: use
  `scripts/neon_http.py pull` → work on `DATABASE_URL=.../finn_mirror` → `push-views research:` etc.
- Workflow after data changes: `finn push` → `finn research <syms>` → `finn export-snapshot` → commit
  → push (deploys).

## Next steps (in order)
0. Owner's list of 13 Nov: (3) GitHub Actions research worker (needs a decision on NSE given the
   refusal), (4) alert defaults vs NIFTY + "moved with no disclosure", (5) Ask bar build-or-remove,
   (6) balance sheet / cash quality / red flags, writeup, diagram, secret scan.
1. Pull depth: more resolvable claims for the hero (quarterly guidance like "Q3 margin", capex
   vs cash-flow capex from annual XBRL), business snapshot / segments from XBRL dims, balance
   sheet & cash quality sections (half-year balance sheets + annual cash flow are in fin_facts).
2. Ask bar (currently disabled with an honest label) — or remove it before submission.
3. Remaining 50 management-change extractions (`public_figures.extract_all(..., limit=8)`), then
   `finn network --seed` (re-plants overlaps) and `finn push`.
4. Phase 6: README/ARCHITECTURE/diagram/WRITEUP, secret scan, make repo public, phone test.
- Gotcha: shell heredocs in this environment turn `\b` into a backspace byte inside Python
  regexes. Edit regex-heavy files with the Write/Edit tools or a script file; check with
  `grep -c $'\x08' file`.

## How to run
```bash
docker compose up -d --wait                         # local Postgres 18 (tests use it)
cd api && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/finn migrate
.venv/Scripts/python ../scripts/pick_portfolio.py   # only to re-pick; writes data/*.json
.venv/Scripts/finn ingest all                       # writes to DATABASE_URL from .env (Neon)
.venv/Scripts/finn counts
.venv/Scripts/uvicorn finn.api.main:app --port 8000
cd ../web && npm install && npm run dev
```
Checks: `cd api && .venv/Scripts/ruff check . && .venv/Scripts/mypy finn && .venv/Scripts/pytest -q`;
`cd web && npm run lint && npx tsc --noEmit && npm test && npm run build`.
Phone over Wi-Fi: build web with `NEXT_PUBLIC_API_BASE=http://<lan-ip>:8000`, start API with
`CORS_ORIGINS=http://<lan-ip>:3000`.

## Gotchas learned
- Next.js 16: no setState synchronously in effects; no `new Date()` during prerender
  (`useSyncExternalStore` with a null server snapshot). Read `web/node_modules/next/dist/docs`.
- Headless Chrome can't go below ~500 px; use CDP device emulation (390×844) for phone checks.
- Git autocrlf: `.gitattributes` forces LF.
- Bash heredocs here can mangle backslashes; use the Write/Edit tools for regex-heavy files.
- yfinance 1.8 works for `.NS` and `^NSEI`. selectolax ≥ 1.0: use `selectolax.lexbor`.
- NSE XBRL: `Four*` (YTD) contexts carry the quarter's dates; parser re-dates them.
