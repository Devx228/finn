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
- **Phase 2 (push core): next / in progress.**
- Keep-alive workflow exists but is OFF (`API_URL` repo variable unset) — private-repo Actions
  minutes. Decide at Phase 6 when the repo goes public.

## Next steps (in order)
1. (Phase 1 done.)
2. Owner-approved: GitHub Actions job for new filings via RSS + rules-only classification +
   alerts — build once the Phase 2 rules classifier exists. Needs a `DATABASE_URL` repo secret
   (ask the owner to add it).
3. Phase 2 plan (work in this order):
   a. `push/classify_rules.py`: NSE `exch_category` + subject regex → reference category +
      sub-type + base score; record `decided_by='rules'`. Start from the real distribution of
      `exch_category` in `filings` (`SELECT exch_category, count(*) ... GROUP BY 1`).
   b. `push/classify_llm.py`: undecided filings, 10 per BULK call, schema per spec §8.1
      (one_line ≤ 18 words enforced in code). Use subject text first; fetch PDF text only if
      the subject is too thin. Choose the local model by measurement: qwen2.5:7b vs 2–3 other
      ≤ 6 GB models on a hand-labelled set (`data/eval/labelled.jsonl`, say the labeller).
   c. `push/bundle.py` (results family within 36 h → one card; duplicates).
   d. `push/results.py`: Revenue / EBITDA (PBT before exceptional + finance costs + D&A − other
      income) / PBT / PAT, QoQ and YoY from `fin_facts`; validate (revenue + other income −
      expenses ≈ PBT; unit sanity); badge verified/unverified. Banks: NII, PPOP, PBT, PAT.
      Source link = the NSE results announcement; data = the XBRL.
   e. `push/score.py` (spec §8.6, components stored for "Why is this here?"), tiers, Now cap 5.
   f. Materialise `brief:<window>` views; API `/api/brief`; web Today: Now cards, Worth rows,
      Buried groups, caught-up line, NSE credit.
   g. Gate: 7-day brief on (emulated) phone with correct tiers and ≥ 5 verified results cards
      whose numbers match the filing PDFs (cross-check 5 by reading the PDF text).
4. Phase 3 network, Phase 4 pull (job table; laptop worker preferred, GitHub-runner worker as
   fallback — design in DECISIONS), Phase 5 all P1, Phase 6 polish. Spec §16.

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
