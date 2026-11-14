# Handoff: how to resume FINN (updated 15 Nov 2026)

## Prompt to paste into a new session (Claude Code or any coding agent)

> You are continuing FINN, an investor-agent app for the ENAM build challenge (deadline
> 15 Nov 2026). Before doing anything, read in this order: `CLAUDE.md` (rules, code map,
> environments, checks), the last checkpoint at the bottom of `PROGRESS.md`, `docs/STATUS.md`,
> the last three dated sections of `docs/DECISIONS.md`, and this file's "Next steps".
> Then run the checks in CLAUDE.md to confirm the tree is green before you change anything.
>
> Rules: the engine (data sources, scoring and ledger rules, research sections) is frozen; work
> is frontend and submission docs. Make additive changes: new components/props/files rather than
> rewrites; do not rename, move or reformat existing files; do not change existing behaviour
> unless that is the task, and then run the tests that cover it. Never invent data: anything the
> app shows must come from stored data with its source, or be hidden. Never print secrets. Follow
> the NSE and zero-spend rules in CLAUDE.md. Log each decision in `docs/DECISIONS.md`, keep
> `docs/STATUS.md` honest, and append a checkpoint to `PROGRESS.md` when you stop.
>
> Work on the first unfinished item in "Next steps" below. Stop after each numbered item, show a
> 390 px phone screenshot (`node scripts/phone_shot.mjs`), and wait for the owner.

## State at this handoff
- Everything through step 8b is pushed; step 8c pre-call card is implemented locally. Checks
  green (92 API tests, 23 web tests). Live push delivery still needs a VAPID keypair in Render.
- Before-design-pass screenshots: `docs/screens/before/` (10 screens × dark/light, plus contact
  sheets `_sheet_dark.png`, `_sheet_light.png`).
- Owner secrets already set: Render `GITHUB_DISPATCH_TOKEN`; GitHub Actions `DATABASE_URL`,
  `GEMINI_API_KEY`, `GROQ_API_KEY`. **Set on 14 Nov:** `GEMINI_API_KEY` on Render (the command bar's model fallback can call Gemini from the API).
## Next steps (owner's list, with the external critic's review of 14 Nov folded in)

**Done on 14 Nov:** 1 (submission package), 2 (event-to-action in the Who-can-help sheet + keep-warm
opener), 3 (results → ledger deep link), 4 (freshness badge), 5 (Who can help on each research
section), 6 (compact Research summary), 7 (rules-first command bar), 8a (Web Push code; live
delivery awaits Render VAPID secrets), 8b (dismissible first-run guide), 8c (cited pre-call card
with replay fallback). **Continue at 8d.** Small follow-ups seen in screenshots: CreditAccess's business snapshot says
"single segment" twice; on cards the first person to call can be a current employee (Research's
sheet ranks former employees first; the card sheet uses the raw ranking).

The critic's verdict: strong technically (architecture 9/10, trust 9/10), weaker on submission
readiness (6/10), mobile density (7/10) and network actionability (6.5/10). Its most urgent point:
**the submission documents contradict the finished app**. With the deadline on 15 Nov, the
recommended order is below; items marked (owner) were requested by the owner, (critic) came from
the review. The owner decides between conflicting items (see "Open decisions").

1. **Submission package (critic; small, urgent).**
   - README: remove "not built" claims for live research and the cost screen; add 3–5 screenshots
     from `docs/screens/`; a 2-minute demo route (below); state deliberate cuts.
   - ARCHITECTURE.md: update limitations and test counts (88 API, 18 web).
   - WRITEUP.md: the 500–700-word covering note (currently a stub).
   - Add a LICENSE (owner to choose) and run a secret scan across the whole git history
     (e.g. `gitleaks detect` or `git log -p | grep` for key patterns) before the repo goes public.
2. **Event-to-action card (critic's "one feature to win"; covers the owner's item 4).** On a results
   or material-event card: the fact, the related promise chain line (from the ledger), who to call
   (existing Who-can-help ranking), the investor's previous meeting note for that company/person
   (synthetic meetings exist in the DB, not yet surfaced), a drafted opener, and actions:
   View promise chain · Copy 3 questions · Copy opener · Open filing. Opener and note must come
   from stored data (template + stored note), never invented.
3. **Results card → Promise Ledger deep link (critic)**: link to the chain(s) that quarter resolved.
4. **Freshness badge on every tab (critic)**: show "Live / Snapshot · as of …" on Research and
   People as Today already does (`Loaded.source` is available from `loadWithFallback`).
5. **"Who can help?" on each research section (owner item 4)**: Business, Financials, Bull/bear.
6. **Compact top summary on Research (critic)**: what changed · what was promised · what to
   investigate · who to call · coverage; chains collapsed (scoreboard already exists).
7. **Command bar (owner item 2)**: rules-first routing (ticker/company → Research; "who knows …"
   → People search); hosted model only for the rest, choosing among existing tools and returning
   typed, cited blocks (≤2 sentences free text), rate-limited; 4 verified example chips.
   Needs `GEMINI_API_KEY` on Render. The critic advises against a generic chat; this design is
   tool-routing with typed cards, not chat, but confirm with the owner before building.
8. **Owner items 3, 5–8**: web push (permission on tap, test button, iPhone note; propose a free
   alternative if unreliable), "Play brief" (browser speech), first-run card, pre-call card,
   filter audit; then the design pass (owner's 9-point list: SVG range bars and sparklines, one
   typeface, ≤3 sizes, card anatomy, colour only for meaning, wordmark/icons, motion only for
   sheets, AA in both themes, empty/loading/error states) with before/after screenshots.
9. **Generalisation evidence (critic)**: run 4 more unseen tickers (incl. a small cap and a
   financial) through the live job queue and report failures honestly. NSE is reachable from
   GitHub runners, so this works from any network.

### Demo route (critic, 2–3 minutes)
Today at 7d (routine filings buried) → HDFC Bank management change (real dossier + second-degree
path) → a results card (verify QoQ/YoY) → CREDITACC research (preliminary outlook, cut, steer,
result, two verdicts) → research an uncached ticker (job progress) → cost ledger (rules first,
caching, ₹0 actual).

### Open decisions for the owner
- ~~Command bar vs the critic's "don't build a chat"~~ **Decided 14 Nov: build it** as the tool-routed design (typed, cited blocks; not a chat). The owner added `GEMINI_API_KEY` on Render.
- Commit `docs/screens/before/` (≈20 PNGs) or keep them out of the repo.
- License choice.

### Known gaps (shown honestly in the app)
- Six filings need the hotspot to fetch text (UltraTech ×3, Sun Pharma ×2, AU Bank): "Not read yet".
- HDFC Bank's 27 Oct card headline lacks the effective date (model line; the person-based line
  could not be confirmed from the text).
- 3 guidance recall misses (docs/evals.md), documented and not fixed (engine frozen).
- CreditAccess and Persistent have no "In the company's words" sentence.
