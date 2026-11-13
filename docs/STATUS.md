# Scope status vs SPEC §3 (updated 2026-11-13, after item 2)

✅ done · 🟡 partial · ❌ missing. Evidence is a file, endpoint or measured output.

## P0

| Item | Status | Evidence |
|---|---|---|
| Windowed digest (24h/3d/7d/30d) in Now / Worth knowing / Buried | ✅ | `api/finn/push/brief.py` writes `brief:<w>` views; Today window picker; PHASES Phase 2 gate |
| Buried pile with counts, each filing openable | ✅ | `web/components/Today.tsx` collapsed "N buried" row → class groups with counts and PDF links |
| Results card (Rev/EBITDA/PBT/PAT, QoQ/YoY) | ✅ | `push/results.py` from XBRL; `ResultsCard.tsx` with EBITDA definition + verified badge |
| Management-change card (bio + network overlap) | ✅ | bio extracted from the company's filing; "You were at ICICI Bank 2014–17" on HDFCBANK |
| Material-event card (→ who to call, why) | ✅ | `network/service.py for_item` → people, call, 3 questions, insider flag |
| One-line "so what"; rest buried | ✅ | classifier one-liners (eval 86.8% end to end, docs/evals.md) |
| Triggered alerts, configurable, in-app inbox | ✅ | defaults by measurement (vs NIFTY, 4×, 6%, results opt-in): 24 in 30 days (was 101); one alert per stock-day; "moved with no disclosure" |
| "Why is this here?" on every item | ✅ | `WhySheet.tsx` shows the score breakdown incl. the network component |
| Research: Business snapshot | 🟡 | segment mix, segment result ÷ revenue, like-for-like YoY from the company's full-year XBRL segment note (13 cos; 9 declare single-segment). No annual-report text cached (all ARs are on NSE, paused), so no "what it does" prose |
| Research: Financial snapshot | 🟡 | latest-quarter revenue/EBITDA/PAT/margins in the trajectory; no TTM, ROE/ROCE, net debt |
| Research: Trajectory | 🟡 | 12 quarters revenue bars + margin line (`Research.tsx`); spec asks 5–10 years + CAGRs |
| Research: Promise Ledger | ✅ | 8 calls (INFY 4); chains given→revised→outcome→verdict; company-reported actuals first; hero KAYNES 5 resolved, CREDITACC 5; say–do line at ≥ 4 |
| Research: Guidance (open, with run-rate) | ✅ | open items show due year; run-rate line for revenue bands ("Needs +8.8% to +12.5% YoY in the remaining 2 quarters"); never for constant-currency bands |
| Research: Bull vs Bear | 🟡 | computed signals from numbers (`research.py signals()`); not 3+3 cited points each for every company |
| Every research claim cited | ✅ | quotes are verbatim-verified and link to the NSE transcript |
| Live pipeline with visible progress for an uncached symbol | ❌ | runs on the laptop only (`finn research SYM`); NSE 403s the hosted API |
| "Who can help?" sheet on Push cards and Research sections | 🟡 | on Push cards ✅; Research has one "Who to call" section, not a chip per section |
| Second-degree paths with strength + evidence | ✅ | `network/graph.py` warmth × overlap; PathLine shows the evidence |
| Direct query "who do I know at / knows about X" | ✅ | free-text search on People over the directory (employer, title, theme, NSE symbol; every word must match; ranked by match then warmth); tested |
| Synthetic network ~70 contacts | ✅ | 72 contacts, 40 meetings, every one tagged synthetic in UI |
| Deployed URL, no login, phone-usable | ✅ | finn-tawny-nine.vercel.app + Render API; Phase 0a phone check |
| Bundled snapshot fallback | ✅ | `web/lib/api.ts loadWithFallback` → `web/public/snapshot/*.json` |
| Cost ledger screen | ✅ | `/api/cost` (view `cost:summary`) + `/cost` screen: calls, cache rate, tokens, failures, by model and task, rules vs model; ₹0 actual; list price shown only where verified |
| README | ✅ | README.md |
| Architecture doc with diagram | ✅ | docs/ARCHITECTURE.md + docs/architecture.svg (WRITEUP still a stub) |

## P1

| Item | Status | Evidence |
|---|---|---|
| Balance sheet section | ❌ | half-year balance sheets are in `fin_facts`, not surfaced |
| Cash quality section | ❌ | annual cash flow in `fin_facts`, not surfaced |
| Red flags section | ❌ | annual reports linked, not read |
| Results card linked to the Promise Ledger | ❌ | |
| Ask bar (tool-calling, typed cards) | ❌ | removed from the UI until it can run on a hosted model from the API (needs a Gemini key as a Render secret) |
| People: expertise map | ✅ | People tab |
| People: coverage gaps (weight vs depth) | ✅ | coverage grid uses `holdings.weight_pct` vs contacts inside |
| People: keep-warm nudges with drafted opener | 🟡 | nudges with the reason; no drafted opener |
| Person dossier | ✅ | "Diligence on a person" sheet (`person_view`) |
| Note resurfacing | ❌ | meetings exist in the synthetic data; not shown against filings |
| Web Push / swipe feedback | ❌ | PWA manifest only |
| Unexplained-move detection | ✅ | "moved with no disclosure": no material filing that session or the two before |
| Classifier eval harness with labelled set | ✅ | `push/evaluate.py` over `data/eval/labelled.jsonl` (114 rows), results in docs/evals.md |
