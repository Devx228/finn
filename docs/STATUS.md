# Scope status vs SPEC §3 (updated 2026-11-15, submission audit)

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
| Research: Business snapshot | 🟡 | segment mix / margins / like-for-like YoY from XBRL segment notes; **what it does**: one verbatim self-description from the latest annual report, page cited (5 of 7 ledger companies; CreditAccess and Persistent: the card says no sentence states it plainly) |
| Research: Financial snapshot | 🟡 | latest-quarter revenue/EBITDA/PAT/margins in the trajectory; no TTM, ROE/ROCE, net debt |
| Research: Trajectory | 🟡 | 12 quarters revenue bars + margin line (`Research.tsx`); spec asks 5–10 years + CAGRs |
| Research: Promise Ledger | ✅ | hero CREDITACC (5 resolved, each checked against its quote), KAYNES second; scoreboard + one timeline per outlook; first vs final guidance verdicts; verbal steers; stricter year rule (POLYCAB 4→0, KAYNES 5→3) · `docs/hero_first.png`, `docs/hero_full.png` |
| Research: compact top summary | ✅ | latest result, ledger pattern + resolved verdict, stored investigation question, top helper and coverage; source/deep links; normal visits keep chains collapsed · `docs/screens/step6_research_summary_dark.png`, `step6_research_summary_light.png` |
| Research: Guidance (open, with run-rate) | ✅ | open items show due year; run-rate line for revenue bands ("Needs +8.8% to +12.5% YoY in the remaining 2 quarters"); never for constant-currency bands |
| Research: Bull vs Bear | 🟡 | computed signals from numbers (`research.py signals()`); not 3+3 cited points each for every company |
| Every research claim cited | ✅ | quotes are verbatim-verified and link to the NSE transcript |
| Live pipeline with visible progress for an uncached symbol | ✅ | POLYCAB gate plus 15 Nov generalisation: unseen SJS, AUBANK, DIXON and TITAN completed on GitHub runners. Each has 12 quarters and 8 calls and is labelled not reviewed; TITAN completed after the legitimate hourly admission window reset. `docs/screens/step9_live_sjs_dark.png`, `step9_live_titan_dark.png` |
| "Who can help?" sheet on Push cards and Research sections | ✅ | every Push card and every Research section (ledger, Business, Financials/Trajectory, Bull-vs-bear) · `docs/screens/status_research_help.png`, `step5_help_sections.png` |
| Second-degree paths with strength + evidence | ✅ | `network/graph.py` warmth × overlap; PathLine shows the evidence |
| Direct query "who do I know at / knows about X" | ✅ | free-text search on People over the directory (employer, title, theme, NSE symbol; every word must match; ranked by match then warmth); tested |
| Synthetic network ~70 contacts | ✅ | 72 contacts, 40 meetings, every one tagged synthetic in UI |
| Deployed URL, no login, phone-usable | ✅ | finn-tawny-nine.vercel.app + Render API; Phase 0a phone check |
| Bundled snapshot fallback | ✅ | `web/lib/api.ts loadWithFallback` → `web/public/snapshot/*.json` |
| Cost ledger screen | ✅ | `/api/cost` (view `cost:summary`) + `/cost` screen: calls, cache rate, tokens, failures, by model and task, rules vs model; ₹0 actual; list price shown only where verified |
| README | ✅ | README.md |
| Architecture doc with diagram | ✅ | `docs/ARCHITECTURE.md` + `docs/architecture.svg`; covering note in `docs/WRITEUP.md` |

## P1

| Item | Status | Evidence |
|---|---|---|
| Balance sheet section | ❌ | half-year balance sheets are in `fin_facts`, not surfaced |
| Cash quality section | ❌ | annual cash flow in `fin_facts`, not surfaced |
| Red flags section | ❌ | annual reports linked, not read |
| Results card linked to the Promise Ledger | ✅ | "FY27 promises" link opens that year's chain · `docs/screens/step3_results_link.png`, `step3_ledger_fy27.png` |
| Command bar (rules first; typed, cited tool blocks) | ✅ | docked above every tab; symbol/company → Research and who-knows → People without a model; fallback model only selects stored tools; 10/hour and 30/day per salted client · `docs/screens/step7_command_result_dark.png`, `step7_rule_people.png` |
| People: expertise map | ✅ | People tab |
| People: coverage gaps (weight vs depth) | ✅ | holding weight vs contacts inside / one step away · `docs/screens/status_coverage_gaps.png` |
| People: keep-warm nudges with drafted opener | ✅ | Stored-fact opener with Copy action plus the filing that makes the call timely · `docs/screens/step2_keepwarm_opener.png` |
| Person dossier | ✅ | 'Diligence on a person': career and education as disclosed in the filing, your overlap, second-degree reach, link to the filing · `docs/screens/status_person_dossier.png`. Known flaw: one parsed span is wrong (Anup Bagchi 'ICICI Bank 1992–now' from 'various leadership positions') |
| Note resurfacing (your meeting notes against a new filing) | ✅ | Stored synthetic meeting note appears in the event's Who-can-help sheet with date and attendees |
| Web Push / swipe feedback | 🟡 | VAPID keys are loaded on Render; tap-only permission, device subscription, automatic deduped Now-card delivery, test alert and exact-card deep link are built. First-device activation-race fix is awaiting deploy and final Android/desktop retest. `docs/screens/step8a_web_push_dark.png` |
| First-run guide | ✅ | Dismissible “three things to try” card with deterministic routes to the 7-day brief, reviewed CREDITACC Research and HDFC Bank People search; restorable from Settings. `docs/screens/step8b_first_run_dark.png` |
| Pre-call card | ✅ | Reviewed holding only; upcoming-date window with an honest replay fallback. LT replay as of 30 Apr 2026 shows the 5 May Q4 result, 15% FY26 guide, +12% 3Q YTD run-rate, implied +22.3% Q4 need, three directly cited questions and existing Who-can-help contact. `docs/screens/step8c_pre_call_dark.png` |
| Filter audit | ✅ | Compares buried and Now tiers with the next two stored sessions at the configured ±6% vs-NIFTY threshold; shows one possible miss and three possible over-ranks in the current 30-day view, with filing links and an explicit non-causality warning. `docs/screens/step8d_filter_audit_dark.png` |
| Mobile design pass | ✅ | One face / three-size type hierarchy, labelled SVG tab icons, SVG evidence graphics, semantic-only colour, AA focus treatment and reduced-motion-aware sheet transitions. CreditAccess duplicate removed; former employees are hard-ranked before current employees. Before/after: `docs/screens/before/`, `docs/screens/after/` |
| Unexplained-move detection | ✅ | "moved with no disclosure": no material filing that session or the two before |
| Classifier eval harness with labelled set | ✅ | `push/evaluate.py` over `data/eval/labelled.jsonl` (114 rows), results in docs/evals.md |

## Network features, checked 2026-11-13 (frontend phase, item 1)

| Feature | Status | Evidence (390 px screenshot) |
|---|---|---|
| Person dossier | ✅ done | `docs/screens/status_person_dossier.png` (People → New faces → Anup Bagchi) |
| Note resurfacing (my meeting notes shown against a new filing) | ✅ done | in the Who-can-help sheet of every card |
| Keep-warm nudges with a drafted opener | ✅ done (opener from stored facts, Copy) | `docs/screens/step2_keepwarm_opener.png` |
| Coverage gaps | ✅ done | `docs/screens/status_coverage_gaps.png` |
| Second-degree paths on the management-change card | ✅ done (HDFC Bank MD & CEO card → sheet: dossier + 3 paths) | `docs/screens/status_mgmt_change_paths.png`. Several other management-change cards still show the exchange label as headline ("Change in Management"): the fact-line rule covers event categories only |
| "Who can help?" on every research section | ✅ done (ledger, business, bull vs bear, financials) | `docs/screens/step5_help_sections.png` |
| Live / Snapshot freshness badge on every tab | ✅ | Today, Research, People · `docs/screens/step4_badge_people.png` |
