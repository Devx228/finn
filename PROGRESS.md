# FINN — progress & handover (read this first)

Kept current with every commit so any agent or model can resume without the chat history.

> **New agent? Start with [`continuing_prompt.md`](continuing_prompt.md)** — it lists what to read,
> the rules (`CLAUDE.md`), how to verify (`bash scripts/verify.sh`) and what to do next
> (`docs/HANDOFF.md`). This file is the running history; the newest checkpoints are at the bottom.

## Current state at a glance (14 Nov 2026)

| Area | State | Where |
|---|---|---|
| Today brief (Now / Worth / Buried, results cards, why-this, alerts with rules) | ✅ live | `push/*`, `web/components/Today.tsx`, `ResultsCard.tsx`, `Alerts.tsx` |
| Ranking from filing text (operational stops, amount vs revenue, order bands, hosted-model fact lines, grounding) | ✅ | `push/severity.py`, `push/pipeline.py`; `docs/ranking_rescore.md` |
| Management-change headlines (who / role / joining or leaving / date) | ✅ (HDFC 27 Oct lacks date) | `push/pipeline.py` `management_lines_stage` |
| Promise Ledger (hero CREDITACC; two verdicts; steers; scoreboard; outlook timelines) | ✅ | `pull/research.py`, `pull/guidance.py`, `web/components/Ledger.tsx` |
| Business snapshot (segment mix; company's words when they describe the whole company) | ✅ | `pull/business.py` |
| Live research for any ticker (job queue, GitHub runner, progress UI) | ✅ gate passed (POLYCAB) | `jobs.py`, `.github/workflows/research.yml`, `ResearchJob.tsx` |
| Network: dossiers (careers as filed), paths, Who can help, coverage, keep-warm, who-knows search | ✅ / 🟡 (no opener, no note resurfacing) | `network/*`, `People.tsx`, `Network.tsx` |
| Cost ledger with verified paid-rate comparison | ✅ | `llm/ledger.py`, `Cost.tsx` |
| Evals (classifier, guidance 26 claims + 25 negatives, ranking regressions) | ✅ | `docs/evals.md`, `data/eval/` |
| Submission docs (README/ARCHITECTURE out of date, WRITEUP stub, no LICENSE) | ❌ next | `docs/HANDOFF.md` step 1 |
| Command bar, web push, first-run, pre-call, filter audit, design pass | ❌ planned | `docs/HANDOFF.md` |


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
- **Ledgers (13 Nov):** KAYNES (hero) 8/8 calls, 5 resolved; CREDITACC 8/8, 3; INFY 4/8, 2; LT 5/8
  (IR site), 1; PERSISTENT 7/8, 0; DEEPAKNTR 4/8, 0; HDFCBANK 4/8, 0 (banks don't guide).
  IR fetch: `finn.sources.ir.IRFetcher` → `data/ir/<SYM>/` → `finn import-transcripts SYM`.
  Refused hosts (never again): `data/cache/IR_REFUSED_*.json` (au.bank.in, infosys.com).
- **Manual transcripts:** `data/manual/<SYM>/manifest.json` + PDFs → `finn import-transcripts SYM`
  → `finn research SYM --offline`. INFY's 4 PDFs (Q3 FY25–Q2 FY26) still needed from the owner.
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

---

## Checkpoint 2026-11-13 (late night): paused at the owner's request

### Done and pushed (live API on Render serves it; Neon updated over HTTPS)
- **NSE**: refusal was the campus Wi-Fi address; works from the phone hotspot and from GitHub
  runners. Stop file cleared by the owner (reason in DECISIONS.md). NSE from the laptop: hotspot only.
- **Item 4, live research jobs**: queue + GitHub runner + limits + progress UI; gate passed (POLYCAB).
- **Promise Ledger**: stricter scoring (year must be named in the quote, etc.); hero = CREDITACC
  (5 resolved), KAYNES second; two verdicts per chain (first vs final guidance, management's
  qualifiers); verbal steers; scoreboard + merged "outlook" timelines; Who can help on the ledger;
  'not reviewed' line on unreviewed reports. Screens: `docs/hero_first.png`, `docs/hero_full.png`.
- **Ranking fix**: event filings scored from their text (finn/push/severity.py); hosted-model fact
  lines; re-score table `docs/ranking_rescore.md`; regression rows in `data/eval/labelled.jsonl`.
- **Annual reports** (7 ledger companies, fetched on the hotspot) → Business snapshot: segment-mix
  "What it does" line, company's own words below only when they describe the whole company.
- **20-claim eval**: `data/eval/guidance_gold.json` (26 claims, 25 negatives); results in
  docs/evals.md (shipped P 0.79 / 23 of 23 year-held, R 0.88, negatives 25/25). 3 recall misses
  documented, not fixed (engine frozen).
- **Three fixes (owner, latest)**:
  1. Filing-bio careers: spans only as the filing states them (org + year in one sentence; else
     "years not stated"; open spans close at the next employer; never "now"); synthetic persona
     ICICI Bank 2014–2019 so the Anup Bagchi overlap is real (2017–2019). All 17 dossiers re-checked.
  2. Management-change headlines: who / role / joining or leaving / date; events confirmed from
     the filing text, never overridden; no exchange label as a headline anywhere ("Not read yet: …"
     or "Nothing beyond the exchange's label: …", both buried).
  3. Business snapshot leads with facts (segment mix); HDFC Bank's product sentence dropped.
- STATUS.md updated with network-feature status + screenshots in `docs/screens/status_*.png`.

### Also done (committed in 8acc52d at this checkpoint)
- Grounding check: every model-written one-line must have its periods/numbers in the filing text
  (or subject when no text): `severity.grounded`, `pipeline.ground_check_stage` (wired into
  `finn push`), test in `api/tests/test_severity.py`. Found by the screenshot review: Persistent
  cards said "Q3" for Q2 filings. Already pushed to Neon (filing_class + brief/alerts/network views)
  and exported to the snapshot.
- `scripts/phone_shot.mjs`: linear-time text lookup (was quadratic and hung on the 30-day page).
- `docs/screens/before/`: the pre-design-pass screenshot set (10 screens × dark/light) was being
  re-taken when paused; contact sheets `_sheet_dark.png`, `_sheet_light.png`. Check all 20 exist;
  re-run the loop in this file's history if not (06 = tap "Ananya Pillai" inside the CG Power card).

### Next, in the owner's order
1. Send the owner the before screenshots (dark + light).
2. **Command bar** (frontend item 2): rules-first routing (ticker/company → Research; "who knows …"
   → people), hosted model only for the rest, choosing among existing tools and returning typed,
   cited blocks; ≤2 sentences of free text; rate-limited; 4 verified example chips.
   **Needs `GEMINI_API_KEY` as a Render secret — ask the owner when starting.** Stop after it.
3. Then (moved up): note resurfacing on a Push card; drafted opener on keep-warm; "Who can help?"
   on each research section.
4. Then: real notifications (web push), first-run card, pre-call card, filter audit, design pass
   (owner's lists in the conversation of 13 Nov).

### Environment notes for resuming
- Campus Wi-Fi blocks Postgres 5432 and NSE. Work against the local copy
  `postgresql://finn:finn@localhost:5432/finn_mirror` (a full dump of Neon taken on the hotspot);
  write back with `scripts/neon_http.py` (allowlisted: views, llm_cache/llm_calls, documents,
  research_set, filing_class). On the hotspot, direct Neon works and NSE may be fetched (laptop).
- Local servers used for screenshots: API `uvicorn finn.api.main:app --port 8000` with
  `DATABASE_URL=…finn_mirror CORS_ORIGINS=http://localhost:3006`; web built with
  `NEXT_PUBLIC_API_BASE=http://localhost:8000` and `next start -p 3006`.
- Still needing the hotspot: text of 4 non-PDF/unfetched filings (UltraTech ×3 resignations,
  rumour clarifications at Sun Pharma ×2 and AU Bank) — they show "Not read yet" and are buried.
- Known data flaws, shown honestly: CreditAccess and Persistent have no "company's words" sentence.

## Checkpoint 2026-11-14 (morning)
- Before-design-pass screenshots complete: `docs/screens/before/` (20 + 2 contact sheets).
- Local web server had been serving a half-replaced build ("Loading brief…" forever); rebuilt and
  restarted. Not a code bug; the live Vercel app was unaffected. Noted in CLAUDE.md gotchas.
- `scripts/phone_shot.mjs` now logs page errors / failed requests (`SHOT_DEBUG=1` for all URLs).
- External critic review received; folded into `docs/HANDOFF.md` "Next steps" with an order and
  open decisions. Agent instructions: `CLAUDE.md` (+ `AGENTS.md` pointer).

## Checkpoint 2026-11-14 (midday)
Done today, all pushed, checks green (85 API / 14 web):
- Submission package: README (walk-through, screenshots, deliberate cuts), ARCHITECTURE (current
  ledger rules, live research, limits, tests), 682-word covering note in docs/WRITEUP.md, MIT
  LICENSE, full-history secret scan (`scripts/secret_scan_history.py`: 0 hits).
- Event-to-action: Who-can-help sheet shows the promise record + chain link, the investor's last
  note, a drafted opener (Copy) and Copy questions; keep-warm openers.
- Results card → "FY27 promises" deep link; Live/Snapshot badge on every tab; Who can help on each
  research section. Screens: `docs/screens/step2_*.png`, `step3_*.png`, `step4_*.png`, `step5_*.png`.
Next: `docs/HANDOFF.md` step 6 (compact Research summary), then 7 (command bar, confirm first), 8, 9.

## Checkpoint 2026-11-14 (step 6: compact Research summary)
- Added a source-linked 20-second brief above the Promise Ledger: latest result, existing ledger
  pattern and top resolved verdict, existing investigation question, top Who-can-help contact,
  calls read and reviewed/not-reviewed status. Empty states never invent missing data.
- Normal Research visits now keep chains collapsed; `?fy=` results-card deep links still open the
  requested chain. No engine, API or stored-data changes.
- Phone evidence in both themes: `docs/screens/step6_research_summary_dark.png` and
  `docs/screens/step6_research_summary_light.png`.
- Baseline shell note: this Windows checkout requires native `api/.venv/Scripts/python.exe` and
  `npx.cmd`; plain `bash` resolved to WSL. Equivalent API/web/secret checks were run natively.
Next: step 7, the approved rules-first command bar with typed, cited model fallback.

## Checkpoint 2026-11-14 (step 7: command bar)
- Added one docked command input above every tab. Deterministic routes handle symbols/company names
  and Who-knows queries; the latter opens People with the existing search populated.
- The hosted fallback is a router, not chat: a Pydantic schema limits Gemini to at most two stored
  tools (brief, filings, research section, Who can help, paths, price stats). Code builds cited
  blocks; the model returns no answer prose and receives no research facts.
- Added per-client/global daily limits without storing prompts or raw IPs, a live NSE-company
  catalog plus bundled fallback, and friendly model-outage behaviour. Tests now 88 API / 18 web.
- All four shipped examples were exercised: two deterministic routes and two real hosted-model
  routes over the local mirror of live data. Phone evidence: `docs/screens/step7_*.png`.
Next: step 8a, web push reliability and a free fallback decision before implementation.

## Checkpoint 2026-11-14 (step 8a: Web Push)
- Added standards-based Web Push with tap-only permission, an iPhone Add-to-Home-Screen note,
  device enable/disable and a rate-limited **Send test alert** action in alert settings.
- The existing push pipeline now sends each new stored 24-hour Now card once to each subscribed
  device. The service worker opens the exact related card in the 7-day brief; the UI expands a
  buried target if needed, scrolls to it and highlights it. No alert fact is model-written.
- VAPID private material remains an environment secret. Code and UI are complete, but live
  delivery is honestly pending `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` on Render.
- Phone evidence: `docs/screens/step8a_web_push_dark.png` and `step8a_web_push_light.png`.
- Tests now 91 API / 20 web.
Next: step 8b, the dismissible first-run “three things to try” card, reachable again from settings.

## Checkpoint 2026-11-15 (step 8b: first-run guide)
- Added a dismissible Today card with three existing product routes: 7-day brief, CREDITACC's
  reviewed Research summary, and People search for HDFC Bank. No model call or new data.
- Dismissal stays on the device; Settings can restore the guide immediately.
- Both-theme phone evidence: `docs/screens/step8b_first_run_dark.png` and
  `step8b_first_run_light.png`. Tests now 91 API / 22 web.
Next: step 8c, the cited pre-call card with replay-date fallback when no event is due in 7 days.

## Checkpoint 2026-11-15 (step 8c: pre-call card)
- Added a reviewed-holdings-only pre-call endpoint and Today card. With no stored upcoming event,
  it explicitly replays LT as of 30 Apr 2026 before Q4 FY26 results on 5 May.
- The replay cutoff prevents hindsight leakage. Stored call guidance (15%) and six pre-cutoff XBRL
  filings produce the 3Q YTD +12.0% run-rate and +22.3% Q4 need. All three questions directly link
  their evidence; Who can help opens LT's existing Ananya Mistry path, labelled synthetic.
- API and bundled snapshot match. Phone evidence: `docs/screens/step8c_pre_call_dark.png` and
  `step8c_pre_call_light.png`. Tests now 92 API / 23 web.
Next: step 8d, the two-sided filter audit with the required causality caveat.

## Checkpoint 2026-11-15 (step 8d: filter audit)
- Added a read-only 30-day tier audit using the next two stored sessions and the existing ±6%
  vs-NIFTY move threshold. It changes no engine rule.
- Current evidence: one buried-then-moved item and three Now-then-quiet items. Every row links its
  filing and shows both stock and relative move; the card explicitly says a move does not prove
  causation. Tests require two later sessions before “quiet” is reported.
- Phone evidence: `docs/screens/step8d_filter_audit_dark.png` and
  `step8d_filter_audit_light.png`. Tests now 92 API / 25 web.
Next: step 8e, the owner’s design pass and the two small known follow-ups.
