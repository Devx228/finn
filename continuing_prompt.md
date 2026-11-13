# Continuing FINN — start here

**If you are a coding agent picking this project up: this file is your brief. Read it fully, then
the files it lists, before you touch any code.** The owner will usually just say "see
continuing_prompt.md". Everything you need is referenced below.

---

## 1. What this project is (one paragraph)

FINN is a mobile-first investor agent for the ENAM build challenge (submission deadline
**15 Nov 2026**). It has three parts. **Push / Today**: every exchange filing for the portfolio is
classified, scored from its own text and ranked into Now / Worth knowing / Buried, with results
cards computed from XBRL and alerts. **Pull / Research**: for any NSE company, a Promise Ledger
reads the last eight earnings-call transcripts, extracts management's numeric guidance verbatim,
chains it (first guidance → revisions → verbal steers → result) and scores it against what the
company reported, plus a business snapshot and trajectory. **Network / People**: 72 clearly
labelled synthetic contacts, real executives' careers as disclosed in filings, second-degree
paths, "Who can help?" sheets, keep-warm nudges and a "who knows X" search. Live on Vercel (web)
+ Render (API) + Neon (Postgres). The quality bar is trust: code computes, models only read, and
anything without evidence is shown as such or hidden.

## 2. Read these, in this order (≈20 minutes)

| # | File | Why |
|---|---|---|
| 1 | `CLAUDE.md` | Rules, owner's hard rules, map of the code, environments, checks, gotchas. **Binding.** |
| 2 | `PROGRESS.md` (read the checkpoints at the bottom first) | What was done, in what order, and the state at each stop. |
| 3 | `docs/HANDOFF.md` | Ordered next steps (owner's list + external critic's review), open decisions, known gaps, demo route. |
| 4 | `docs/STATUS.md` | Every feature marked done / partial / missing, with screenshot evidence. |
| 5 | `docs/DECISIONS.md` (the last 5 dated sections) | Why the current rules exist. Each fixed a real, documented failure. |
| 6 | `docs/ARCHITECTURE.md` + `docs/architecture.svg` | Data flow: sources → worker → rules/XBRL/LLM → Postgres views → read-only API → Next.js → snapshot fallback. |
| 7 | `docs/evals.md` | Measured quality (classifier, guidance extraction with negatives, ranking regressions). |
| 8 | `docs/SPEC.md` | The original product spec (long; skim sections you touch). |
| 9 | `web/AGENTS.md` | This Next.js version has breaking changes; read before writing web code. |

Screens to look at before UI work: `docs/screens/before/_sheet_dark.png`, `_sheet_light.png`,
`docs/hero_first.png`, `docs/screens/status_*.png`.

## 3. Before you change anything

1. `bash scripts/verify.sh` must print **"OK: all checks green"** (API lint + types + 85 tests;
   web lint + types + 14 tests + build; no secrets tracked). If it doesn't, stop and report;
   don't "fix" unrelated code.
2. `git status` should be clean. `git log --oneline -15` shows recent work.
3. If you need data locally, follow "Environments" in CLAUDE.md (local copy `finn_mirror`,
   HTTPS write-back via `scripts/neon_http.py`).

## 4. How not to deteriorate what exists

- **The engine is frozen**: no new data sources, companies, scoring/extraction/ledger rules or
  research sections. (Only exception the owner allowed: Trajectory to multi-year from XBRL.)
- **Additive only**: new components, props, endpoints, files. Don't rewrite, rename, move or
  reformat existing files; don't "tidy" code you aren't asked to change. If a change to existing
  behaviour is the task, keep it minimal and run the tests that cover it.
- **Files with dense, test-pinned logic — change only if the task is about them:**
  `api/finn/pull/guidance.py`, `pull/research.py`, `pull/reported.py`, `push/severity.py`,
  `push/classify_rules.py`, `push/pipeline.py`, `push/brief.py`, `network/service.py`,
  `network/graph.py`, `jobs.py`, `sources/http.py`, `web/lib/alerts.ts` (mirrors `push/alerts.py`).
- **Never invent data.** Every number, quote, date or name shown must come from stored data with
  its source. Model-written text must pass `severity.grounded`. No evidence → hide it or say so.
- **Never** delete `data/cache/SOURCE_REFUSED.json` or `IR_REFUSED_*.json`, print keys, or fetch
  from NSE on campus Wi-Fi (see CLAUDE.md).
- After each change: `bash scripts/verify.sh`, a 390 px screenshot of what changed
  (`node scripts/phone_shot.mjs <url> <out.png> '<steps>' dark|light`), a dated entry in
  `docs/DECISIONS.md`, `docs/STATUS.md` updated, a checkpoint appended to `PROGRESS.md`, then
  commit and push.

## 5. What to do next

Take the first unfinished item in **`docs/HANDOFF.md` → "Next steps"**. At the time of writing:

1. Submission package: README/ARCHITECTURE contradictions, 500–700-word `docs/WRITEUP.md`,
   screenshots in the README, demo route, LICENSE (owner chooses), git-history secret scan.
2. Event-to-action card on results / material-event cards (promise line, who to call, previous
   meeting note, drafted opener, copy questions/opener, open filing).
3. Results card → Promise Ledger deep link. 4. Live/Snapshot · as-of badge on every tab.
5. "Who can help?" on each research section. 6. Compact top summary on Research.
7. Command bar (confirm with the owner first; needs `GEMINI_API_KEY` on Render).
8. Web push, first-run card, pre-call card, filter audit, design pass. 9. Four more unseen tickers.

**Stop after each numbered item**, show the screenshot, and wait for the owner's go.

## 6. The prompt (paste this into a new agent)

> You are continuing **FINN**, a mobile-first investor agent for the ENAM build challenge
> (submission deadline 15 Nov 2026). The repository is in the current directory. A lot of careful
> work exists and is live (web on Vercel, API on Render, Postgres on Neon). Your job is to move it
> forward **without degrading anything that already works**.
>
> **1. Read first, in this order, before touching code:** `continuing_prompt.md` (this file),
> `CLAUDE.md` (binding rules, code map, environments, checks, gotchas), the newest checkpoints at
> the bottom of `PROGRESS.md`, `docs/HANDOFF.md` (ordered next steps, decisions, known gaps, demo
> route), `docs/STATUS.md`, the last five dated sections of `docs/DECISIONS.md`, and
> `web/AGENTS.md` (this Next.js version has breaking changes). Look at
> `docs/screens/before/_sheet_dark.png` and `_sheet_light.png` to see the current UI.
>
> **2. Prove the baseline:** run `bash scripts/verify.sh`. It must end with
> "OK: all checks green" (85 API tests, 14 web tests, lint, types, build, no tracked secrets).
> `git status` must be clean. If either fails, stop and report; do not fix unrelated code.
>
> **3. Rules you must follow:**
> - The engine is frozen: no new data sources, companies, scoring, extraction or ledger rules,
>   and no new research sections. Work is frontend and product glue on top of existing data.
> - Additive changes only: new components, props, endpoints and files. Do not rename, move,
>   reformat, refactor or "clean up" existing files. If a task needs an existing behaviour
>   changed, keep the change minimal and run the tests that cover it. The files listed in
>   `continuing_prompt.md` §4 hold dense, test-pinned logic: change them only if the task is
>   about them.
> - Never invent data. Every number, quote, date and name on screen comes from stored data with
>   its source, or is hidden or labelled ("not scored", "not read yet"). Model-written text must
>   pass `severity.grounded`; model calls return structured output that code checks.
> - Never print or commit secrets. Zero spend: free tiers only. Do not fetch from NSE unless the
>   owner says the laptop is on the phone hotspot (campus Wi-Fi is refused); never delete
>   `data/cache/SOURCE_REFUSED.json` or `IR_REFUSED_*.json`.
> - Bash heredocs on this machine mangle `` and other backslashes: write regex-heavy code with
>   the file Edit/Write tools, and check for `chr(8)` afterwards.
>
> **4. What to build, in order** (details in `docs/HANDOFF.md` "Next steps"; items 1–5 are done):
> - **Step 6, compact summary on Research:** a top block a busy investor reads in 20 seconds:
>   what changed (latest results line), what management promised (the ledger's one-line count and
>   the most important resolved verdict), what to investigate (from the existing ledger
>   questions), who to call (the existing Who-can-help top contact), and coverage (calls read,
>   reviewed or not). Built only from fields already in the research view; chains stay collapsed
>   below it.
> - **Step 7, command bar** (owner approved; `GEMINI_API_KEY` is set on Render): one input
>   docked above the tab bar on every screen. Rules route first: an NSE symbol or a company name
>   opens Research; "who knows / who do I know at …" opens the People search (existing
>   `web/lib/whoKnows.ts`). Only when rules can't route, a new API endpoint calls the hosted
>   model, which may only choose among existing tools (brief, filings, research section,
>   who-can-help, paths, price stats) and returns typed blocks that the app renders with existing
>   components. At most two sentences of free text; every block cites its source; research
>   answers use stored report data only, never the model's knowledge. Rate-limit it per client
>   and per day (follow the pattern in `api/finn/jobs.py`). Add four example chips, each verified
>   to work on live data.
> - **Step 8:** web push (permission asked only on a tap, a "Send test alert" button, a one-line
>   iPhone note about Add to Home Screen, tapping opens the card; if web push is unreliable,
>   propose a free alternative before building it); then the first-run card ("three things to
>   try", dismissible, reachable from settings); the pre-call card (a reviewed-ledger holding with
>   results or a call in the next 7 days: date, promises falling due with range and run-rate,
>   three cited questions, Who can help; use the "as of" replay date if none is upcoming); the
>   filter audit (buried filings followed within two sessions by a move beyond the alert
>   threshold, and Now items followed by no move, with "a price move doesn't prove the filing
>   caused it"); then the design pass (owner's list in HANDOFF.md, with before/after screenshots
>   against `docs/screens/before/`).
> - **Step 9:** run four more never-researched tickers (including a small cap and a financial)
>   through the live job queue and report failures honestly.
> - Small known follow-ups: CreditAccess's business snapshot says "single segment" twice; on
>   cards the first person to call can be a current employee (rank former employees first, as the
>   Research sheet already does).
>
> **5. After each step:** run `bash scripts/verify.sh`; take a 390 px phone screenshot of what
> changed (`node scripts/phone_shot.mjs <url> <out.png> '<steps json>' dark|light`, saved under
> `docs/screens/`); add a dated entry to `docs/DECISIONS.md`; update `docs/STATUS.md` and the
> "Done" line in `docs/HANDOFF.md`; append a checkpoint to `PROGRESS.md`; commit with a clear
> message and push. Data changes go to Neon through `scripts/neon_http.py` (allowlisted
> write-back) when working on Wi-Fi. Then **stop, show the owner the screenshot, and wait** before
> the next step.
