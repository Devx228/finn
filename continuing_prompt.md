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

## 6. The prompt (if you want to paste one)

> Continue FINN. Read `continuing_prompt.md` and every file it lists, in order, before touching
> code. Run `bash scripts/verify.sh` and confirm it is green. Then work on the first unfinished
> item in `docs/HANDOFF.md` "Next steps", following the rules in `CLAUDE.md` (engine frozen,
> additive changes only, never invent data, never rewrite working files). After the item: run
> `scripts/verify.sh`, take a 390 px screenshot, log the decision in `docs/DECISIONS.md`, update
> `docs/STATUS.md`, append a checkpoint to `PROGRESS.md`, commit and push, then stop and show me.
