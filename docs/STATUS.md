# Scope status vs SPEC §3 (as of 2026-11-13, before the Promise Ledger rework)

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
| Triggered alerts, configurable, in-app inbox | 🟡 | `push/alerts.py` + `web/lib/alerts.ts`, tested both sides; **defaults fire 101 in 30 days — too noisy**; no "no disclosure" mark |
| "Why is this here?" on every item | ✅ | `WhySheet.tsx` shows the score breakdown incl. the network component |
| Research: Business snapshot | ❌ | not built (no segment / what-it-does section) |
| Research: Financial snapshot | 🟡 | latest-quarter revenue/EBITDA/PAT/margins in the trajectory; no TTM, ROE/ROCE, net debt |
| Research: Trajectory | 🟡 | 12 quarters revenue bars + margin line (`Research.tsx`); spec asks 5–10 years + CAGRs |
| Research: Promise Ledger | 🟡 | per-metric band history + verdicts from **4** calls; INFY 2 resolved; CC guidance "not comparable"; no say–do score |
| Research: Guidance (open, with run-rate) | 🟡 | open bands shown in the tracker; no run-rate line ("needs +x% in H2") |
| Research: Bull vs Bear | 🟡 | computed signals from numbers (`research.py signals()`); not 3+3 cited points each for every company |
| Every research claim cited | ✅ | quotes are verbatim-verified and link to the NSE transcript |
| Live pipeline with visible progress for an uncached symbol | ❌ | runs on the laptop only (`finn research SYM`); NSE 403s the hosted API |
| "Who can help?" sheet on Push cards and Research sections | 🟡 | on Push cards ✅; Research has one "Who to call" section, not a chip per section |
| Second-degree paths with strength + evidence | ✅ | `network/graph.py` warmth × overlap; PathLine shows the evidence |
| Direct query "who do I know at / knows about X" | 🟡 | symbol chips + expertise-map themes on People; no free-text search |
| Synthetic network ~70 contacts | ✅ | 72 contacts, 40 meetings, every one tagged synthetic in UI |
| Deployed URL, no login, phone-usable | ✅ | finn-tawny-nine.vercel.app + Render API; Phase 0a phone check |
| Bundled snapshot fallback | ✅ | `web/lib/api.ts loadWithFallback` → `web/public/snapshot/*.json` |
| Cost ledger screen | 🟡 | every call logged to `llm_calls` with list-price USD (`llm/store.py`); **no `/api/cost`, no screen** |
| README | ❌ | no README.md at repo root |
| Architecture doc with diagram | ❌ | not written; WRITEUP.md is a 17-line stub |

## P1

| Item | Status | Evidence |
|---|---|---|
| Balance sheet section | ❌ | half-year balance sheets are in `fin_facts`, not surfaced |
| Cash quality section | ❌ | annual cash flow in `fin_facts`, not surfaced |
| Red flags section | ❌ | annual reports linked, not read |
| Results card linked to the Promise Ledger | ❌ | |
| Ask bar (tool-calling, typed cards) | ❌ | `AskBar.tsx` is a disabled input — visible and half-built |
| People: expertise map | ✅ | People tab |
| People: coverage gaps (weight vs depth) | ✅ | coverage grid uses `holdings.weight_pct` vs contacts inside |
| People: keep-warm nudges with drafted opener | 🟡 | nudges with the reason; no drafted opener |
| Person dossier | ✅ | "Diligence on a person" sheet (`person_view`) |
| Note resurfacing | ❌ | meetings exist in the synthetic data; not shown against filings |
| Web Push / swipe feedback | ❌ | PWA manifest only |
| Unexplained-move detection | ❌ | (planned as the "moved with no disclosure" alert mark) |
| Classifier eval harness with labelled set | ✅ | `push/evaluate.py` over `data/eval/labelled.jsonl` (114 rows), results in docs/evals.md |
