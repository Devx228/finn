# Decision log

Append-only. Each entry: date, decision, alternatives considered, why. Facts checked against
live sources are marked **VERIFIED** with the source and the date checked; anything not yet
checkable is marked **PENDING** with what will settle it.

---

## 2026-11-12 — Ground rules set by the owner

- **Zero spend is the only hard limit.** No paid API, host, or plan; nothing that needs a card
  or billing account, including "free with card on file". The spec's paid-credit fallback
  (§6.1, §17) and Cloud Run (§5.1) are removed. If a service asks for a card, stop and report.
- **Scope:** all of P0 and all of P1, in the spec's phase order. A feature is correct on real
  data or hidden.
- **Local-first:** everything runs locally (Ollama, Postgres in Docker, `.env` defaults). Every
  external service is swappable by env vars only.

## 2026-11-12 — Repository and documents

- The brief, reference and spec were at the project root under their original names, not in
  `docs/`. Copied to `docs/brief.pdf`, `docs/reference.pdf`, `docs/SPEC.md`; originals left in
  place and git-ignored.
- `enam-afe` sat inside a git repo rooted at the owner's home directory. Ran `git init` inside
  `enam-afe` so the project has its own history.

## 2026-11-12 — Spec corrections approved by the owner (applied to docs/SPEC.md as we go)

1. Phase 0 split into **0a (local gate)** and **0b (deployed gate)**; accounts are created
   after 0a passes.
2. **Ingest runs on the owner's laptop** (local Ollama is the BULK tier) and writes to the
   hosted Postgres. GitHub Actions does CI and keep-alive. Addition: test whether BSE's
   announcements API answers a GitHub Actions runner; if yes, a light cloud job fetches new
   filings, classifies with rules only, and evaluates alerts. Model enrichment stays local.
   If BSE blocks the runner, laptop-only and the UI shows "data as of …". — PENDING (Phase 1).
3. **Promise Ledger extraction:** local, page by page first; measure recall, precision and
   verbatim-quote accuracy (citation verifier) against hand-listed claims from 2 transcripts;
   repeat on Gemini once a key exists; choose by the numbers; record in `docs/evals.md`.
4. **Live research:** 4 transcripts on a live run, 8 for precomputed companies; after a live
   run, extend to 8 in the background if quota allows.
5. **Screener:** read terms and robots.txt and report them to the owner before any scraping.
   Prefer numbers parsed from filings; label Screener-sourced numbers.
6. Use the reference's category names everywhere (§8.5 used `m_and_a`, `capex_expansion`,
   `litigation_regulatory`; replaced by `M&A`, `capex`, `litigation`).
7. §4.1 referenced "rules classifier (section 7.2)": the classifier is §8.1 and built in Phase
   2. `pick_portfolio.py` gets a minimal headline tagger in Phase 1.
8. DPDP dates in §12 to be verified before they appear in the writeup. — PENDING.
9. `seed_overlaps` stays; synthetic label stays in the UI; the writeup says fictional contacts
   are planted as ex-colleagues of real, named executives.

## 2026-11-12 — Backend host: Render (Hugging Face Spaces ruled out)

**VERIFIED 2026-11-12:**
- **Hugging Face Spaces — ruled out (needs a paid plan).** Official docs: "Gradio and Docker
  Spaces run on compute and require a paid plan to create: PRO for personal accounts…"
  (huggingface.co/docs/hub/en/spaces-overview) and "Without a subscription, creating,
  duplicating or moving a Gradio or Docker Space on `cpu-basic` fails with a payment error
  (HTTP 402)" (huggingface.co/docs/huggingface_hub/en/guides/manage-spaces). Only static
  Spaces and ZeroGPU Gradio Spaces are free, and neither can run the FastAPI service.
- **Render — chosen, subject to the sign-up showing no card prompt.** render.com/docs/free
  lists free web services and does not require a payment method to deploy; the only
  payment-method text concerns overage ("If you haven't added a payment method, Render instead
  suspends all of your Free services for the remainder of the month"). Free web services
  spin down after 15 min without inbound traffic; spin-up "takes about one minute"; 750 free
  instance hours per workspace per month (enough for one always-on service: 744 h in a
  31-day month); no persistent disk; may restart at any time. RAM/CPU not stated on that
  page (third-party sources: 512 MB, 0.1 CPU) — PENDING confirmation at sign-up.
- **Koyeb — not usable as fallback.** Official pages would not load (TLS error from the
  fetcher). Recent third-party sources (snapdeploy.dev, srvrlss.io) report a card has been
  required since Feb 2026. Treated as card-required unless the owner sees otherwise.

**Consequences:** the cold start (~1 min) is the main demo risk. Mitigations already in the
spec: keep-alive ping every ~10 min (stays inside 750 h), warm-up `GET /health` on app load,
Vercel GET caching, snapshot fallback after 4 s. The API image binds to `$PORT` (default 7860,
Render injects its own).

## 2026-11-12 — Database: Neon (PENDING account)

Third-party summaries (neon.com/blog, neon.com/faqs, agentdeals.dev) agree: free plan with no
card, no expiry, 100 CU-hours/project/month, scale-to-zero after 5 min idle, storage 1 GB per
project (older pages say 0.5 GB). To be confirmed on the Neon console at sign-up. Our data
volume (18 companies × 120 days of filings with page text, 8 transcripts × ~30 companies) must
be measured against 0.5–1 GB in Phase 1; if page text overflows, keep page text only for
documents that reach a deep read.

## 2026-11-12 — LLM providers: what is actually free

**VERIFIED 2026-11-12 (official docs):**
- **Cerebras — ruled out (needs a payment method).** inference-docs.cerebras.ai/support/
  rate-limits: "New accounts receive $5 in free credits after adding a verified payment
  method"; "Is there a permanently free tier? No. The Free Trial is time- and credit-bounded";
  "If you skip adding a payment method at sign-up, Playground and API access remain inactive
  until you do." Under the zero-spend rule this is excluded. Not signing up.
- **Groq — usable; no card for the Free plan** (billing FAQ: a payment method is needed only
  to upgrade to Developer). Free plan, from console.groq.com/docs/rate-limits (table not
  labelled Free in the extracted text, but its values match the Free plan, far below the
  Developer figures):

  | Model | RPM | RPD | TPM | TPD | Context | strict JSON schema | tools |
  |---|---|---|---|---|---|---|---|
  | openai/gpt-oss-120b | 30 | 1K | 8K | 200K | 131K | yes | yes (no parallel) |
  | openai/gpt-oss-20b | 30 | 1K | 8K | 200K | 131K | yes | yes (no parallel) |
  | qwen/qwen3.8-27b | 30 | 1K | 8K | 200K | 131K | yes | yes (parallel) |

  Structured outputs and tool use cannot be combined in one call on Groq. **8K TPM means one
  request cannot carry a full transcript**: Groq is for short prompts only (Ask agent,
  classification, why-them / questions). Exact numbers to be re-read from response headers
  once a key exists.
- **OpenRouter — usable as a low-volume fallback.** openrouter.ai/docs/api-reference/limits:
  `:free` models get 20 RPM and **50 requests/day** unless ≥ 10 credits were ever purchased
  (we will not purchase). The page doesn't say whether `:free` needs a card — PENDING at
  sign-up.
- **Gemini — PENDING (needs a key).** Google no longer publishes free-tier numbers; the live
  limits appear only in AI Studio per project. Third-party reports from Sep–Oct 2026
  (tinkerllm.com, aipromptshub.co) suggest roughly Flash 5 RPM / 20 RPD and Flash-Lite
  10–15 RPM / 500 RPD, with Pro removed from the free tier. If Flash is really 20 RPD, the
  REASON tier must be budgeted to ~20 calls/day and the ingest must be spread across days.
  To be confirmed from AI Studio and response headers, along with: availability from India,
  the OpenAI-compatible endpoint, and image/PDF input.

**Revised provider plan (§6.1):**

| Tier | Order |
|---|---|
| BULK (ingest) | Ollama local → Gemini Flash-Lite (long docs, scanned pages) |
| BULK (live, deployed) | Gemini Flash-Lite (long) · Groq gpt-oss-20b / qwen3.8-27b (short) → OpenRouter `:free` |
| REASON | Gemini Flash → Groq gpt-oss-120b → OpenRouter `:free` |
| VISION | Gemini Flash-Lite (rendered page images) |

Local model: candidates measured in Phase 1 (qwen2.5:7b already installed, plus 2–3 others
from the Ollama library that fit 6 GB), chosen on JSON validity, accuracy on real filings,
VRAM and tokens/s.

## 2026-11-12 — docs/SPEC.md edited to match approved changes

Seven edits, each marked inline with *[Changed 2026-11-12 …]*: §4.1 cross-reference (headline
tagger), §5.1 backend host (Render), §5.1 scheduler (laptop ingest), §6.1 REASON tier (no paid
fallback), §8.5 category names, §16 Phase 0 split into 0a/0b, §17 no paid credit.

## 2026-11-12 — Phase 0a implementation choices

- **View-models in one table.** `views(key, body jsonb, as_of)`; keys like `brief:24h`. The API
  read path is a single `SELECT`; the ingest is the only writer. Snapshot export dumps the same
  rows to `web/public/snapshot/<key>.json`, so live and snapshot share one shape by construction.
  Alternative considered: one table per view type — deferred until a view needs querying by
  column (Phase 2 `brief_items` will be a real table; the brief view is materialised from it).
- **Plain SQL migrations** applied by `finn migrate` (also on container start), not Alembic:
  fewer moving parts; the schema is written by hand anyway.
- **Snapshot fallback in the client**, with a 4 s timeout (`NEXT_PUBLIC_API_TIMEOUT_MS`). Unit
  tested for: live success, HTTP error, timeout, both failing.
- **Next.js 16.4 (cacheComponents on).** Two rules it enforces that shaped the code: no
  synchronous `setState` inside effects (load results are tagged by window; "loading" is
  derived), and no clock reads during prerender (today's date uses `useSyncExternalStore` with
  a `null` server snapshot).
- **Phone-width check without a phone in the loop:** headless Chrome has a ~500 px minimum
  window, so plain `--window-size=390` screenshots crop. Evidence uses Chrome DevTools
  Protocol device emulation (390×844, mobile, touch, iPhone UA) and reports `scrollWidth` to
  prove no horizontal scroll.
- **Line endings:** `.gitattributes` forces LF (the owner's git uses autocrlf; the Dockerfile
  and future shell scripts run on Linux).

## 2026-11-12 — Gate 0a passed on the owner's phone

Owner opened `http://<laptop-lan-ip>:3000` on their phone over Wi-Fi and confirmed it works
(Live badge from the API; snapshot fallback shown in emulation with the API stopped).

## 2026-11-12 — Phase 0b preparation (before accounts exist)

**VERIFIED 2026-11-12 (official docs):**
- **Render Blueprint** (render.com/docs/blueprint-spec): `type: web`, `runtime: docker`,
  `plan: free` (0.1 CPU, 512 MB), `region: singapore` valid (cannot be changed after
  creation), `dockerContext` / `dockerfilePath` relative to repo root, `healthCheckPath`.
  `autoDeploy` is deprecated → `autoDeployTrigger: commit`. `envVars … sync: false` not
  confirmed from the fetched text; if the Blueprint rejects it, the two secrets are set in the
  dashboard instead.
- **Vercel Hobby** (vercel.com/docs/plans/hobby, /limits): no card; "restricts users to
  non-commercial, personal use only" — a personal job-application prototype is within that;
  flagged to the owner. 100 GB fast data transfer, 1M function invocations, 100
  deployments/day, 300 s max function duration. Hobby cannot connect to repos owned by a
  GitHub organisation → the repo lives under the owner's personal account.
- **Neon Free** (neon.com/docs/introduction/plans, /regions): no monthly cost, no card stated
  for the database; 1 GB storage per project (20 GB total), **100 CU-hours/project/month**,
  scale to zero after 5 min (cannot disable), 5 GB egress/month. Singapore
  (`aws-ap-southeast-1`) available on Free. Chosen region: Singapore, next to Render's
  Singapore region.

**Decision: keep-alive must not wake the database.** A keep-alive every 10 min that touched
Postgres would keep Neon's compute awake almost continuously (~0.25 CU × 720 h ≈ 180 CU-h,
above the 100 CU-h cap, after which Neon suspends compute for the rest of the month). Added
`GET /livez` (process only, never opens a DB connection; tested) for the keep-alive and as
Render's health check. `/health` still checks the DB and is what the web app calls on load, so
Neon wakes only for real use (sub-second resume).
- Alternatives: no keep-alive (every first visit pays Render's ~1 min cold start); keep-alive
  on `/health` (exhausts Neon compute). Chosen: `/livez`.
- Render budget: one always-on free service ≈ 720–744 of 750 free instance hours/month.

## 2026-11-12 — Gate 0b passed; deployment frozen at "good enough"

Web: https://finn-tawny-nine.vercel.app (Vercel Hobby, root `web`). API:
https://finn-api-mxni.onrender.com (Render free, Docker, Blueprint). DB: Neon free, Postgres 18;
local Postgres and CI moved to 18 to match. Evidence (CDP-emulated 390×844 iPhone): live page
shows "Live" from Neon via Render; with `*onrender.com*` blocked in the browser, the same page
shows "Snapshot" from the bundled JSON; no horizontal scroll either way.

- Repo is **private** for now (Devx228/finn). GitHub's free plan gives private repos 2,000
  Actions minutes/month, and a 10-minute keep-alive bills ~4,300 (each run rounds up to a
  minute). The keep-alive stays off (`API_URL` unset) until the repo is public or the owner
  picks an external pinger. Cold start (~1 min) is covered by the snapshot fallback meanwhile.
- Owner's direction: priority is now core functionality. No further infrastructure work beyond
  what each gate needs; redeploy after each phase passes locally.

## 2026-11-12 — Phase 1 source probes (spec §7.1–7.4 do not hold as written)

**VERIFIED 2026-11-12, from the owner's laptop (plain requests, polite rate):**
- **NSE symbol master** `nsearchives.nseindia.com/content/equities/EQUITY_L.csv`: 200, 2,635
  rows; columns SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT,
  ISIN NUMBER, FACE VALUE.
- **Yahoo via yfinance 1.8.0**: works for `.NS` and `^NSEI`; today's bar present.
- **BSE announcements API** (`api.bseindia.com/.../AnnSubCategoryGetData/w`) and BSE scrip
  list: **403 Access Denied** (CDN block). Not retried with browser-session tricks: that would
  be bot-check circumvention (the coding agent's own guardrail refused it, correctly). BSE is
  dropped as a source.
- **NSE announcements API** (`www.nseindia.com/api/corporate-announcements`): 200 JSON to a
  plain request, no cookies. RELIANCE, 120 days → 58 rows with `desc` (category), `attchmntText`
  (subject), `attchmntFile` (PDF on nsearchives), `an_dt`, `sm_isin`, `hasXbrl`. Concall
  transcripts are identifiable from `attchmntText`.
- **NSE annual reports** (`/api/annual-reports`): PDF links per financial year.
- **NSE financial results** (`/api/corporates-financial-results`, `/api/results-comparision`):
  structured results filings (consolidated/standalone, audited, period) and line items as
  numbers — a primary, exchange-sourced numeric spine. Freshness/coverage to be checked.
- **NSE RSS** (`nsearchives.nseindia.com/content/RSS/Online_announcements.xml`): published
  feed, ~1 day rolling window (1,103 items today) — good for incremental ingest, no backfill.
- **NSE robots.txt**: `Allow: /`, only `/market-data-test` disallowed. NSE's terms-of-use page
  timed out from the fetcher — PENDING (owner to open it in a browser).
- **Screener.in terms** (screener.in/guides/terms/): licence for "personal, non-commercial
  transitory viewing only"; may not "modify or copy the materials", use them "for any public
  display (commercial or non-commercial)", or "mirror the materials on any other server".
  robots.txt does not block company pages, but the terms forbid what §7.4 needs (store tables,
  display them publicly). **Not scraped.**

**Proposed change (awaiting owner):** NSE replaces BSE (§7.3) and Screener (§7.4). Filings,
annual reports, transcripts and structured results all from NSE — every source primary.
Datacenter reachability (Render, GitHub runners) still to test; if blocked, live research on
the deployed app needs the laptop or degrades honestly.

## 2026-11-12 — NSE is the single data source (owner decision)

**Decision:** NSE for filings, annual reports, transcripts and quarterly numbers. BSE and
Screener dropped. The source layer sits behind an adapter interface so another source can be
added later.

**Terms (owner-verified):** NSE's terms of use prohibit systematic/automated data collection and
republishing without permission, as Screener's do. The owner proceeds because the brief
explicitly directs candidates to NSE/BSE filings and this is a personal, non-commercial
evaluation prototype. Mandatory access rules, enforced in code where possible:
1. Never bypass or work around a block, bot check or rate limit. If NSE refuses, stop and tell
   the owner.
2. Minimum footprint: one request at a time, ≥ 1 s apart, cache everything, never re-fetch a
   document we already have.
3. Fetch only what the app needs: portfolio and research companies, plus on-demand tickers.
   No bulk crawling.
4. Never re-host PDFs. Store extracted text for analysis; show short cited quotes and computed
   numbers; link to the original document on NSE.
5. Attribute NSE as the source in the UI.
6. The writeup states what was accessed, how, and that production would use a licensed
   exchange data feed (`docs/WRITEUP.md`).

## 2026-11-12 — Pre-Phase-1 probes (owner's four questions)

All requests one at a time, ≥ 1.5 s apart, cached; ~20 NSE requests in total for all probes.

**1. Depth of structured results.**
- Two NSE endpoints together cover the full history: `corporates-financial-results` (XBRL XML,
  up to Dec 2024) and `integrated-filing-results` (SEBI Integrated Filing, Mar 2025 →; HTML
  rendering of the XBRL). The first endpoint simply stops at Dec 2024 — that is the format
  change, not missing data.
- Quarters available (consolidated / standalone): RELIANCE 54 / 80 (from 2005), INFY 60 / 80
  (2005), PERSISTENT 57 / 56 (2010), NAVINFLUOR 23 / 70 (cons 2019, std 2007), CREDITACC
  19 / 24 (2018), KAYNES 9 / 9 (listed 2022), HDFCBANK 23 / 80, BAJFINANCE 28 / 79; plus
  6–7 integrated quarters each (Mar 2025 → Sep 2026).
- Statements: verified in RELIANCE Mar-2024 XBRL and Sep-2026 integrated filing — **P&L,
  balance sheet, cash flow and segments**, plus (integrated) the auditor-opinion declaration and
  a notes block with ratios. BS and CF appear in half-year filings (Q2, Q4). Not yet verified for
  older years; by regulation half-yearly balance sheets go back to ~2015 and half-yearly cash
  flows to H1 FY20, so expected depth is ~10 years P&L, ~10 years BS, ~6–7 years CF — to be
  measured per company in Phase 1.
- Gap-fill from annual reports (only if a section needs years the structured data lacks, e.g.
  CF before FY20): locate the three statements by text search (code), send those ~3–6 pages to
  BULK once per annual report; each report gives two years. ≈ 2–3 local calls per company,
  ≈ 40–60 calls for the full demo set, on Ollama (zero cost, ~10k-token prompts). Recommended:
  skip unless the measured depth is short — Cash quality needs 3+ years, which CF already has.

**2. Transcripts.** Two-year announcement history, transcripts identified from `attchmntText`:
RELIANCE 9, INFY 12, PERSISTENT 9, KAYNES 10, CREDITACC 9, NAVINFLUOR 9 rows — 8 of the last
8 quarters for all six. Spot-checked two that a "link/website" pattern flagged: both full-text
transcripts (RELIANCE Q2 FY27: 29 pages, 16,623 words; NAVINFLUOR Q1 FY27: 17 pages, 8,319
words). No link-only filings seen in this set.

**3. Banks and NBFCs.** NSE flags format per filing (`bank`: N, B = bank, F = NBFC in older
filings). HDFCBANK's integrated filing is the bank format: interest earned, operating profit
before provisions, % gross/net NPA, CET1, deposits, segments, cash flow. BAJFINANCE's is the
Ind AS format (revenue from operations, finance costs, total assets, cash flow, segments) with
no NPA rows in the table. One alias map per format; never assume a row exists.

**4. Datacentre access.** GitHub-hosted runner (IP 57.154.6.42): **200**, JSON, 0.46 s.
Render (Singapore): **403 Access Denied** — not retried. Temporary probe workflow and endpoint
removed after the run.
- Consequences: the server never calls NSE. Laptop ingest as planned. The cloud
  rules-only filings + alerts job on GitHub Actions is feasible. Live research uses the owner's
  job-table design: the app inserts a job row; a worker claims it, runs the pipeline and writes
  progress rows the UI polls; "queued — worker offline" when no worker heartbeat is recent.
  The README will document running a worker locally for any ticker.

## 2026-11-12 — Phase 1 build decisions

- **Owner direction (Phase 4 scope, recorded now):** GitHub-runner research worker approved as
  the *fallback* to the laptop worker (one job table, either may claim; laptop preferred when
  its heartbeat is recent). Fine-grained token scoped to this repo, Actions-dispatch only,
  stored as a Render secret. Abuse protection: symbol validated against the NSE master, cached
  report returned if present, one job per symbol, 1–2 concurrent runs, per-IP and per-day rate
  limits. UI shows runner start-up honestly. Owner to be told when hosted model keys are needed.
- **Polite client** (`sources/http.py`): process-wide lock, ≥ 1.2 s between NSE requests,
  disk cache keyed by URL (documents forever, listings 6 h, symbol master 7 days), one retry
  only for timeouts/5xx. Any 401/403/429 or "Access Denied"/captcha page raises
  `SourceRefused`, writes `data/cache/SOURCE_REFUSED.json`, and every later run refuses to call
  until a person deletes the marker. Tested.
- **XBRL is the numeric spine; integrated filings also ship XBRL XML**, so one parser covers
  2005 → today. Every numeric fact is stored as reported (`fin_facts`: concept, dims, period,
  value in absolute INR); metrics are computed from facts in code per format later.
- **NSE XBRL quirk (verified on RELIANCE Q4 FY24):** year-to-date contexts (`Four*`) are declared
  with the quarter's dates but carry YTD values (FY24 revenue ₹9,14,472 cr vs Q4 ₹2,40,715 cr;
  cash flow appears only in YTD). The parser re-dates `Four*` contexts from the filing's own
  `DateOfStartOfFinancialYear`. Pinned by a fixture test.
- **Which XBRL filings are fetched (minimal footprint):** every quarter in the last 16 (QoQ, YoY,
  guidance checks) plus every Mar/Sep half-year end in the last 10 years (balance sheet, cash
  flow, full year). Per period: consolidated if filed, else standalone; `basis` stored per row so
  a series switch is always labelled, never silently spliced. Latest revision wins.
- **Filing PDFs fetched lazily.** All announcements are stored as metadata (category, subject,
  NSE PDF link). PDF text is fetched only for filings a later stage must read (management change,
  M&A, capex, litigation), via `finn ingest texts`. Results PDFs (4–8 MB each) are not needed:
  the numbers come from XBRL.
- **Portfolio picked by `scripts/pick_portfolio.py`** from real filings (40 NSE requests, one per
  candidate, same 120-day window the ingest reuses from cache): DEEPAKNTR, KPITTECH, SUNPHARMA,
  TATASTEEL, TITAN, ULTRACEMCO, VBL, HDFCBANK, BAJFINANCE, AUBANK, CGPOWER, M&M, BHARTIARTL,
  DIXON, LT, MARUTI, PERSISTENT, PIIND — 10 themes, 2 banks, 1 NBFC, 6 small/mid caps (size
  buckets approximate: ≥ ₹1 lakh cr large, ≥ ₹30k cr mid). Weights and entry dates synthetic
  (seeded). Research set: INFY (guidance hero), KAYNES (mid-cap capex), CREDITACC (NBFC), TRENT
  (0 transcripts in 120 days — degradation demo; a large cap, not the small cap the spec asked
  for).
- **Caveat on the picker's evidence:** the minimal tagger reads NSE's generic category text
  ("Resignation of Director/KMP/SMP"), so its "KMP change" count includes non-executive
  directors (e.g. Noel Tata retiring from Tata Steel / Titan). Which changes are CEO/CFO/MD level
  is verified from PDF text after ingest, before Phase 3 relies on it.
- **Tests never touch Neon:** `tests/conftest.py` points DATABASE_URL at TEST_DATABASE_URL
  (default local docker Postgres); DB tests skip if it is down.

## 2026-11-12 — Phase 1 results and what they changed

- **Measured fundamentals depth** (per company in `coverage:<SYMBOL>`): NSE publishes XBRL for
  results only from mid-2018; earlier quarters have an HTML results page
  (`resultDetailedDataLink`) instead. Balance sheet and cash flow appear in XBRL only from ~2022
  (9 half-year balance sheets, 3–4 annual cash flows). Against the spec's needs — Trajectory 5–10
  years (we have ~8 FY of P&L), Cash quality 3+ years (we have 3–4) — this is enough, so per the
  owner's rule the annual-report gap-fill is **skipped**. Pre-2018 HTML pages remain an option
  for a 10-year trajectory; not fetched.
- **Fiscal years are read from the filings, not assumed April–March:** VBL reports on a calendar
  year. Annual figures are identified by period length (≥ 360 days), and display labels must use
  each company's own year end.
- **404s:** NSE lists 3 XBRL files its archive doesn't have (e.g. an HDFCBANK 2021 bank XBRL). A
  404 is not a refusal: the row is recorded with the error (never requested again) and the other
  basis for that period is tried.
- **Management changes verified from PDF text** (not the generic category label): real top-level
  changes in the portfolio — HDFCBANK (new MD & CEO, Anup Bagchi, "in place of" the incumbent)
  and ULTRACEMCO (MD completing his term 31 Dec 2026); research set — INFY (CEO Designate). M&M
  filed an appointment with a full bio (ex-MD, Cummins India). TITAN (independent director) and
  DIXON (MD re-appointment) are correctly routine. Spec's "≥ 2 real management changes" is met.
- **Router smoke test:** qwen2.5:7b on Ollama 0.5.13 returned valid JSON but labelled a capacity
  commissioning "M&A" (should be capex). The local model will be chosen by measurement on a
  labelled set in Phase 2, and the rules stage will catch this pattern before any model sees it.

## 2026-11-13 — Phase 2 decisions

- **Local BULK model = qwen2.5:7b, chosen by measurement** (docs/evals.md): v2 prompt 59% on the
  hard 54 vs qwen2.5:3b 44%, llama3.1:8b 28% (v1). Prompt v2 changes that mattered: batch 5
  instead of 10 (small models dropped/renumbered items), text starting at the letter's "Sub:"
  line instead of the letterhead, two few-shot examples.
- **Rules take everything with a deterministic signal** (v3: 100% on the 76 labelled filings
  they decide; 79% of all filings). Added after reading eval misses (disclosed): ESG ratings,
  investor conferences, call recordings, monthly volumes, results releases, registrar address
  changes, re-appointments, and a top-role change stated inside a "General Updates" letter (the
  model had called HDFC Bank's MD & CEO disclosure "M&A").
- **Results cards from XBRL, not PDFs:** zero model calls for numbers; validation = the filing's
  own identities; QoQ/YoY only on the same basis; no % change against a loss base. Badge
  "verified" means the filing's arithmetic holds; PDF cross-check is a separate gate step.
- **Scoring weights** (spec §8.6) unchanged; magnitude for results = |PAT YoY| / 3 capped at 20;
  price reaction = 2 points per 1% abnormal return vs NIFTY, or 3 × volume multiple when ≥ 2×,
  capped at 10, on the first session that could react (same day if filed before 3 pm IST).
- **Replay (`as_of`)** builds the brief live from stored data (no model calls) and never uses
  prices after the as-of time. One price query per brief instead of per item: 8.5 s → 1–2 s
  locally, 0.6 s on Render.
- **Portfolio moved into the DB** (`holdings`, `research_set`) because the deployed API image
  has no `data/` folder. `finn ingest holdings` loads it.
- **Gap noted:** insider trades (PIT) and promoter pledges (SAST) are not in NSE's announcements
  feed; only takeover-code declarations appear. Those two categories are thin until a source for
  those disclosures is added.

## 2026-11-13 — Model one-liners attached to the wrong filing: found and fixed

While building Phase 3 I read the management-change list and found model one-liners describing a
*different* company's filing (DEEPAKNTR's filing summarised as an AU Small Finance Bank
re-appointment; a Sun Pharma filing as a Maruti price increase). Cause: in a batch of five, the
small model sometimes misaligns items. Measured: 5 of 252 one-liners named another demo company
(the true rate is higher — swaps with non-demo content are invisible to that check).

Fix (prompt `classify_batch-v3`):
1. Each filing in a batch carries a short `ref` (hash of the filing id) the model must echo; an
   answer whose ref doesn't match is rejected and the filing retried in another batch. 24 of 252
   answers were rejected across the re-run.
2. Batches are grouped by company, so a residual swap cannot cross companies.
3. Post-check: a one-liner that names a company absent from the filing's own subject/text is
   dropped (the cleaned exchange subject is shown instead) and the reason records why.
Result after re-classifying all 252: 1 one-liner named another company (dropped by the
post-check); 3 filings stayed misaligned on every retry and are shown as "not yet classified"
rather than given a wrong label.

## 2026-11-13 — Network in the brief, pull engine, alerts
- **Network scoring stays code.** Warmth × overlap (paths) and relevance × warmth (who to call)
  per spec §9; the investor's own CV is compared too ("You were at ICICI Bank while they were
  there") because a first-degree overlap beats any path. Network points feed the brief score.
- **Guidance: rules first, model second.** qwen2.5 7B alone found 1 of 2 Infosys guidance items;
  rules over pre-selected sentences (management only, cue word + number) catch the common
  phrasings, pair each metric keyword with its nearest number (multi-metric sentences), and skip
  questions, analyst paraphrases, outcomes ("ended at… against guidance") and segment growth. The
  model adds what rules miss; any item whose quote isn't verbatim in the transcript is dropped.
- **Constant-currency guidance is not scored against ₹ growth.** Shown as "not comparable".
- **Alerts evaluated client-side** over a materialised input view (90 sessions + material
  filings), mirrored in Python with a shared test fixture. Rules live in the browser
  (localStorage) — per-viewer settings, no account needed for the demo.
- **Pull is a worker job, not on-demand from the hosted API**: NSE returns 403 to Render. The
  research page says this instead of faking a live run.

## 2026-11-13 — Hosted model limits, measured (owner added Gemini + Groq keys)
Measured with tiny calls (Groq: `x-ratelimit-*` headers; Gemini: burst until 429, quota from the
error body). Daily caps on Gemini were not hit and are not reported by the API.

| Provider · model | Measured | Notes |
|---|---|---|
| Groq · openai/gpt-oss-120b, gpt-oss-20b, qwen/qwen3.8-27b | 1,000 requests/day, **8,000 tokens/min** per model; 131k context | TPM is the binding limit: ~4 transcript-sized calls/min |
| Gemini · gemini-3.5-flash-lite | **15 requests/min** (16 accepted in 27 s, then 429 `GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, value 15) | stable |
| Gemini · gemini-3-flash-preview | **5 requests/min** (429 quotaValue 5) | |
| Gemini · gemini-3.8-flash | works, but 503 "high demand" on ~half of probes | the API's recommended model |
| Gemini · gemini-3.1-pro-preview | 429 on first call (input-token quota 0) | **not on the free tier** |
| Gemini · gemini-2.5-* | 404 "no longer available to new users" | |

Router: throttle is now per provider:model (Gemini 3.5-flash-lite 14/min, 3-flash 5/min, Groq
4/min); on 429/5xx it waits 20 s and retries the same model once before falling to the next.

## 2026-11-13 — Promise Ledger rework; NSE refused the laptop; DB over HTTPS
- **NSE refused us (403, Akamai "Access Denied") on the first transcript fetch from the laptop**,
  2026-11-13 03:05 IST (`data/cache/SOURCE_REFUSED.json`). Per the access rules: stopped, no
  retries, file left in place, owner told. Effect: ledgers read 4 of the last 8 calls (the 4 older
  transcripts were never fetched). Not worked around (no other IP, no GitHub runner for this).
- **This network resets Postgres on 5432** (TLS reset, even with direct TLS); Neon's HTTPS SQL
  endpoint works. `scripts/neon_http.py` mirrors Neon → local `finn_mirror` over 443 and writes
  views / cache / ledger rows back. Dev aid only; the product still uses the normal driver.
- **Constant-currency guidance resolves against the company's own reported cc growth** (full year
  from the Q4 call, YTD from Q1/H1/9M statements), quoted and cited, labelled "company-reported,
  constant currency"; ₹ growth shown beside it as context. No more "not comparable".
- **Filing-checkable metrics:** capex (cash-flow PPE purchases vs plan, pace-checked YTD), loan
  growth (balance-sheet loans YoY; labelled — AUM includes off-book), credit cost (impairment ÷
  average loans, annualised YTD), ROA, ROE. Cost-to-income and NIM not scored (definitions can't
  be rebuilt from XBRL lines). Segment targets, open-ended aspirations and multi-year totals are
  listed, never scored. Years without results are "pending".
- **Extraction tier `EXTRACT`** = gemini-3-flash → gemini-3.5-flash-lite → gpt-oss-120b → local,
  picked on the eval in docs/evals.md; rules first, model adds non-conflicting items, strict check.
- **Second hero: CREDITACC** — six numeric FY27 targets, four checkable straight from filings
  (loan growth, credit cost, ROA, ROE), two raised mid-year; all on track at H1. It resolves when
  FY27 closes (or when the older calls with FY26 guidance can be read). KAYNES gives the only
  rupee-checkable *resolved* pair today (FY26 growth ~50% guided vs 33.2% → missed; EBITDA margin
  15.6% vs 15.8% → delivered).

## 2026-11-13 (later) — NSE diagnosis, transcripts from company IR sites, safe write-back
- **NSE refusal, diagnosed from local logs only (no new NSE requests):** refused URL
  `nsearchives.nseindia.com/corporate/Infosys_21102025214121_SEfiling_Earningscalltranscript_q2.pdf`
  — same host and `/corporate/` path as the 24 transcripts fetched fine; 0 requests in the 10 min
  before (last NSE response 18:31:58Z, refusal 21:35:27Z, a 3 h 03 min gap); it was the first and
  only request of that process (no warm-up, no retry). infosys.com (also Akamai) returned the same
  "Access Denied" to a plain client minutes later. Read: the network/IP, not our rate. Owner is
  checking the URL in a browser; all automated NSE fetching stays stopped (no GitHub job calls NSE).
- **Manual transcript import** (`finn import-transcripts SYM`): PDFs in `data/manual/<SYM>/` +
  `manifest.json` (original URL, call date, quarter); stored like fetched ones with
  `documents.source = 'company IR site, manually downloaded'` (migration 0006); the citation links
  the company's own URL; PDFs are gitignored (never re-hosted). Owner asked for the download to be
  done for them: CREDITACC ×4 and KAYNES ×4 came from the companies' sites with a plain client;
  infosys.com refused (Akamai) and was not worked around — owner downloads those 4 by hand.
- **Write-back to Neon is allowlisted** (`scripts/neon_http.py`): views only under pipeline-owned
  prefixes; llm_cache insert-only; llm_calls appended without ids; documents inserted by url,
  never overwriting text; any other table refused; the remote comes only from `.env` and must be a
  Neon host. The first run of the insert-only ledger push hit a duplicate id (Neon's sequence was
  behind after the earlier unsafe push) and failed instead of overwriting — sequence advanced.
- **More precision guards from 8-call ledgers:** speaker attribution (analysts named by the
  moderator, and the moderator, never count as management), number-before-metric phrasing
  ("4.2%-4.5% ROA"), increments ("additional", "another", run-rate, half-year) skipped, multi-year
  totals beat a named year, "FY25-26" = FY26, unit-consistent chains (bps never joins a % chain),
  a lender's bare "growth" = loan growth, bare "margin" = EBITDA margin at EBITDA reporters,
  constant currency decided per company, lower credit-cost guidance shown as good news.
- **EXTRACT order changed:** gemini-3.5-flash-lite first. 3-flash timed out on 48 of 57 calls on
  13 Nov; it scored the same 1.00/1.00 as flash-lite in the pipeline on the gold set.

## 2026-11-13 (night) — Hero = KAYNES; true source labels; company IR sites
- **Owner decision:** KAYNES is the Promise Ledger hero, CREDITACC second; INFY stays on 4 of 8
  calls as the guidance-cut / constant-currency example. Gate (SPEC §16): hero ≥ 5 resolved, fully
  cited promises. KAYNES: 5 (2 delivered, 3 missed), each with quote + page + transcript link and
  the XBRL filing behind the actual.
- **Labels are true:** files FINN fetched from a company site live in `data/ir/<SYM>/` and are
  labelled "company IR site"; only files the owner places in `data/manual/` are "downloaded by
  hand". The 8 earlier records were relabelled locally and on Neon.
- **Company IR fetcher** (`finn/sources/ir.py`): robots.txt first and obeyed; one plain request
  per file (honest User-Agent, no header tricks, no retries), 5 s apart; cached; the first refusal
  writes `data/cache/IR_REFUSED_<host>.json` and that host is never contacted again (tested).
  Results: persistent.com 3 files; investors.larsentoubro.com 5; www.au.bank.in **refused (403)**
  on its listing page — stopped for good; www.infosys.com refused earlier — marker recorded;
  godeepak.com TLS certificate fails verification — skipped (not disabling verification); other IR
  listing pages render links with JavaScript, so URLs came from web search, guessed variants
  limited to 3 per file.
- **Review of every resolved claim on the new ledgers removed:** CAGR / "over five years" targets
  read as one year (L&T Lakshya 13–15%, Persistent 19–20% CAGR); "Net Working Capital to Revenue
  … 12%" read as revenue growth; L&T's P&M-portfolio margin and its finance subsidiary's loan-book
  and credit-cost targets scored against the consolidated company; "ROE printed … 16.6%" (an
  actual); an analyst's "you guys … 16% was the target". Rules added: multi-year markers, segment
  words before the number make it segment-scope (one segment point makes the whole chain segment),
  a non-lender's loan-book metrics are a subsidiary's.

## 2026-11-13 (late) — The company's own number decides; README / ARCHITECTURE / diagram
- **Owner rule (SPEC §10.3):** when the company reports the guided metric itself, that number is
  the actual (quoted, cited, "company-reported"); our computed figure decides only where the
  filing is unambiguous (revenue, rupee revenue growth, EBITDA margin) and is otherwise a
  cross-check. Implemented generically in `finn/pull/reported.py` (no per-company code):
  management sentences stating a result, number right after its metric word, the nearest period
  marker decides (a quarter marker disqualifies), multi-year sentences skipped.
- Effects: CREDITACC FY26 loan growth / ROA / ROE now resolve on the company's figures (14.0% /
  2.7% / 10.7%; ours 15.0 / 2.6 / 10.5 shown as cross-checks); its real FY26 guidance from the May
  2025 call (14–18%, ROA 2.9–3.4%, ROE 11.8–13.3%) was being missed ("aiming" not a cue; the
  continuation sentence had no cue) — both fixed generally. L&T FY26 growth: the company itself
  says "growth for FY26 stood at 12% compared to our guidance of 15%" (group revenue) → missed,
  cited. Tolerance cut to rounding (±0.05): the company calls its FY26 ROA of 2.7% vs 2.9–3.4% "a
  marginal miss", and so do we now.
- "unverifiable" renamed "not scored"; open items show their due year; the hero is read from
  `data/research_set.json` (role "hero: …"), not from code. No more companies, no more IR fetching.

## 2026-11-13 (late) — Alert defaults chosen by measurement; "moved with no disclosure"
Grid over the last 30 days, 18 holdings (volume × {2, 2.5, 3, 4}, move {3–7%}, absolute vs
relative to NIFTY): the old defaults (2×, ±4%, absolute, results included) fired **101**.
Results filings were 28 of the 43 filing alerts — they reach the brief every quarter anyway — so
they are opt-in now. New defaults: **moves relative to NIFTY, volume ≥ 4×, |move| ≥ 6%, material
categories (M&A, management change, litigation, fund raise, capex, rating)**; a stock's volume and
price alerts on one day are one alert; identical filing lines collapse. Result: **24 in 30 days,
8 in the last 7** (14 filings, 7 price, 3 volume) — about six a week. A market alert is marked
**"moved with no disclosure"** when the company made no *material* filing that session or in the
two sessions before (trading sessions, not calendar days — a Monday move answers Friday's
results): 3 in 30 days, all CG Power (5–6 Nov falls; its closure-order stay was disclosed 7 Nov).
Saved rules use a new storage key so old defaults don't linger. Python and TypeScript evaluators
share one fixture and four identical tests.

## 2026-11-13 (late) — Ask bar removed for now; "who knows X" built without a model
- **Ask bar removed** from the UI (owner: build it on a hosted model or remove it). Building it
  properly means the API calls a model at request time, which needs a Gemini key as a Render
  secret (owner action) and breaks the zero-model read path; a disabled control is half-built and
  visible. Revisit when the key is on Render.
- **Free-text "who do I know at X / who knows about Y"** on People: deterministic search over a
  directory materialised into `network:home` (each contact's employers with years, titles, org
  themes, mapped NSE symbols). Every query word must match; ranked by where it matched (current
  employer > past employer = symbol > theme > title > name) then warmth. Tested.

## 2026-11-13 (evening) — NSE diagnosis, live research jobs, disclosure fix, verified prices
- **NSE refusal was the campus address.** One request to the exact URL refused on campus Wi-Fi
  (Infosys Q2 transcript), same client and headers, from a phone hotspot: HTTP 200,
  `application/pdf`, 611,615 bytes. The `SOURCE_REFUSED.json` marker stays until the owner deletes
  it (the agent was not permitted to move it, correctly); the laptop stays stopped until then.
  Direct Postgres to Neon also works on the hotspot, so the HTTPS mirror is no longer needed there.
- **Live research job queue** (`finn/jobs.py`, migration 0007, `.github/workflows/research.yml`).
  App → `POST /api/research/jobs` → validated against the NSE master in `companies` → cached report
  returned if it exists → one active job per symbol (unique partial index; a second request joins)
  → 3 new tickers/hour and 6/day per client (salted hash of the IP, never stored raw), 20/day total
  → at most 2 running. Runner: the laptop worker (`finn worker`, heartbeat every 15–30 s) if seen in
  the last 90 s, else the API dispatches one GitHub Actions run for that job id; the run only claims
  the job row, so the dispatch input can't name a ticker or command. Runner start-up is shown as
  measured (dispatch → claim, median and max over past runs), never a promised number; a run that
  hasn't started in 10 min or stops reporting for 12 min is failed with the reason. A refusal from
  NSE is written to `source_blocks` (origin `github`) permanently: FINN then never sends work there
  and the app says a new ticker can't be fetched until the laptop is online.
- **"Moved with no disclosure" was wrong twice for CG Power.** The owner asked to see the filing
  timestamps beside the price dates: CG Power filed a closure-of-operations disclosure (litigation)
  at 12:35 on 5 Nov, inside the session, but the classifier scored it 34 and the rule only counted
  filings scored ≥ 40. The rule now counts every event-category filing whatever its score (only
  administrative categories — unclassified, investor meetings, call intimations, AGM/EGM, postal
  ballot — are excluded unless scored ≥ 40): the claim is factual, so it errs towards "there was a
  disclosure". Result: one no-disclosure alert in 30 days (CG Power, 15 Oct, −5.2%, −6.9% vs NIFTY;
  no filing on 13–15 Oct before the close; an ESOP allotment came at 16:24, after it).
- **Paid list prices verified** from the providers' own pages (2026-11-13): Gemini 3.5 Flash-Lite
  $0.30/$2.50 and Gemini 3 Flash Preview $0.50/$3.00 per 1M in/out (aistudio.google.com/docs/
  pricing, paid tier, standard); Groq gpt-oss-120b $0.15/$0.60 and qwen3.8-27b $0.80/$4.00
  (console.groq.com/docs/models). The ledger shows hosted calls at those rates ($0.10) and the local
  model's tokens priced as Gemini 3.5 Flash-Lite ($0.25); cache hits spent no tokens. Shown in USD:
  no exchange rate is verified, so none is applied.
- **NSE stop file cleared by the owner (2026-11-13).** Reason: the refusal on 12 Nov came from the
  campus Wi-Fi address; the same URL with the same client loaded from a phone hotspot (HTTP 200,
  PDF). NSE may resume **from the laptop on the hotspot only**, under the same rules (one request at
  a time, ≥ 1.2 s apart, cached, permanent stop on any refusal). Check before any laptop NSE run:
  Neon's Postgres port must be reachable directly, the sign that the laptop is on the hotspot and
  not campus Wi-Fi (which blocks 5432); if it isn't, don't fetch.

## 2026-11-13 (night) — Stricter scoring after the first live run (POLYCAB)
The first unreviewed live report (POLYCAB, job 2) showed four "delivered/beat" verdicts. All four
were wrong when read against their quotes: an achievement ("we have achieved our ₹200 bn goal")
scored as FY26 revenue guidance; a reported figure ("calendar 2024 top-line stands at ₹210 bn")
as FY25 guidance; an export-mix target ("share of international business north of 10% of
revenue") as FY25 revenue growth; and a segment's past EBIT restated as EBITDA, chained with a
yearless long-term 11–13% band, as an FY26 margin "beat". New rules, for every ledger:
- **A claim is held to a year only if its quote names the year or period** ("FY26", "this year",
  "the financial year", "next year"). Otherwise it is listed as "no year stated", never resolved.
  A year named in the continuation sentence right after counts (it is quoted with it).
- Achievements, figures that "stand at", "would have been" restatements and mix targets ("share
  of", "% of revenue") are results or other measures, never guidance.
- A revenue target already met by trailing revenue when it was stated is a restated goal: not scored.
- Verdicts: beat = clearly beyond the band; delivered = within it or meeting a floor ("at least",
  "15% plus", "in excess of"); missed = short.
- Guided and actual more than 30% apart → not scored as a suspect match, unless the quote names
  that exact fiscal year.
- Reports not in the hand-checked research set, and every live run, carry "Generated
  automatically (time); not reviewed." The say–do line still needs ≥ 4 resolved claims.
Effect: POLYCAB 4 → 0 resolved. **KAYNES 5 → 3**: "FY26 revenue growth missed" was scored on a
quote about the automotive segment with no year; "FY26 EBITDA beat" on "might exceed the guidance
of 15.6%" with no year; FY25 margin is now "delivered" (a 15%-plus floor met), not "beat". KAYNES
no longer meets the hero gate (≥ 5); CREDITACC (5) does. Hero choice left to the owner.
CREDITACC, INFY, LT unchanged in count. Regression cases: data/eval/guidance_negatives.json and
tests in api/tests/test_pull.py.

## 2026-11-13 (night) — Hero = CreditAccess; two verdicts per chain; verbal steers
- **Hero: CREDITACC; KAYNES second** (owner). Gate: ≥ 4 resolved promises, each checked against its
  quote by FINN and the owner; a wrong verdict is the failure, not a low count.
  `data/research_set.json` now lists all eight reviewed ledger companies.
- **Two verdicts per chain**: against the FIRST guidance for that year and the LAST before the
  result, in one line with management's own qualifier ("Missed preliminary 18–20% outlook · met the
  lowered 14–18%, at the very bottom of the range"). A promise met only after a cut shows "met after
  cut", never plain "delivered". If the first statement read is itself a revision ("revise …
  upward"), the original is in a call not read: it is said, and not scored as original.
  Say–do reports both ("met final guidance 1 of 5 · met original guidance 0 of 5"), and a one-line
  pattern is generated from those counts only.
- **Verbal steers**: an analyst states a number or range, management's reply opens by explicitly
  confirming or rejecting it → recorded with both lines verbatim, attached to the chain carrying
  that exact range (skipped if it fits more than one metric). No number is invented
  (CREDITACC 28 Oct 2025: "Yes, we should assume at the lower end of the bracket.").
  A yearless "we retain our guidance of X" with exactly an open chain's range reiterates that chain.
- Floor words count only beside the point's own number ("15% plus" in a neighbouring sentence no
  longer turns "₹2,800–2,900 cr" into a floor).
- Hero page: each chain is a timeline (date, speaker, call and page, the qualifier, the quote around
  that step's own number, what changed, steers, result, both verdicts); every step opens the PDF
  at that page.
- Data fetched on the hotspot (no refusals): the 7 ledger companies' FY2026 annual reports (7
  requests, ~101 MB) and the text of 39 event filings from the last 30 days that had never been read
  (needed for the ranking fix). A full copy of Neon is in the local Docker DB for work on Wi-Fi.

## 2026-11-13 (late night) — FOUND AND FIXED: ranking scored whole categories without reading them
**Failure.** CG Power's 5 Nov filing "Action(s) taken or orders passed" was a pollution board
directing closure of its Waluj plant. One rule gave every filing in that NSE category a flat 34
without reading it, no model wrote a summary, and the card's headline was the exchange's generic
label. Same pattern elsewhere: every L&T order win 38 regardless of size; QIPs, press releases and
FDA approvals rated by a small local model or not at all; "Press release on 20 October 2026" shown
as a summary. Found by the owner checking the "moved with no disclosure" claim.
**Fix (finn/push/severity.py, pipeline.severity_stage / fact_lines_stage).** No event category
(orders passed, order wins, share sales, press releases, acquisitions, capex) keeps a flat score
without its text being read: (1) operational stop (closure, suspension, licence cancelled, search,
attachment) → top tier; (2) else the rupee amount at stake for that kind of event (penalty, order
value, amount raised, consideration, outlay; never per-share prices or cumulative figures) as a
share of the company's own trailing revenue; L&T-style order classes via the band table printed in
the same filing; a company statement of "no material impact" caps it; (3) else the hosted model
rates it from the text. Every event filing gets a one-line fact from the hosted model, pointed at
its own item in multi-item board letters; a line that says nothing is discarded and the item is
buried; an operational stop falls back to the filing's own sentence. Routine sub-types (results
decks, monthly volumes, subsidiary incorporations, debt allotments) keep flat scores.
**Checked by reading the filings:** Maruti's ₹13,000 cr is a *favourable* ITAT order (positive
tax impact; contingent liability cut by ₹6,300 cr; "no major impact on financials") — capped at
38, not promoted. The under-40 management changes are not CEO/MD/CFO changes (CCO, CISO, SMP,
independent/non-executive directors, an ED re-appointment); two UltraTech resignations have no
text (not PDFs) and wait for the hotspot. Rumour clarifications at Sun Pharma (×2) and AU Bank
also have no text and stay unscored-by-text until fetched.
**Result:** 7-day Now gains CG Power's High Court stay of the closure order; 30-day Now gains both
CG Power filings (closure order and stay). 70 filings: base up 14, down 13, unchanged 43; tiers
buried→worth 4, worth→now 1, worth→buried 10. Full table: docs/ranking_rescore.md. Hosted-model
ratings varied between runs before caching (Bajaj QIP launch 18 vs 51; Sun Pharma ILUMYA 45 vs 39):
answers are cached now, so they are stable, but the model's rating is a judgment, not a measurement.
Labelled set +10 rows (124); 4 existing rows gained expected ranges; L&T #795 relabelled
worth→buried (a ₹1,000–2,500 cr order is under 1% of L&T's revenue).

## 2026-11-14 — Submission package (critic's review, step 1)
- README, ARCHITECTURE and WRITEUP brought in line with the built app: live research and the cost
  screen are built (no longer "not built"); test counts 85 API / 14 web; ARCHITECTURE §3 states the
  current ledger rules (year must be named, two verdicts, steers), §8 live research, §9 known limits;
  the NSE refusal outcome (campus address) recorded in §5.
- README: a 3-minute walk-through matching the live screens, three screenshots, deliberate cuts,
  licence. `docs/WRITEUP.md`: the 682-word covering note (data-access notes kept below it).
- LICENSE: MIT (owner's choice).
- Secret scan across the full git history (`scripts/secret_scan_history.py`, patterns for Google,
  Groq, GitHub, Neon, Postgres URLs with passwords, private keys): 0 hits in 45 commits.
- **Freshness on every tab** (critic): Research and People now show the same "Live / Snapshot · as of"
  badge as Today (`components/FreshnessBadge.tsx`), so stale snapshot data is never unlabelled.
- **Results card → Promise Ledger** (critic): a results card's link reads "FY27 promises" and opens
  `/research?s=SYM&fy=FY27`, which opens and scrolls to that year's chain (resolved first).
- **Event to action** (critic's "one feature to win"; owner item 4): every card's "Who can help?"
  sheet now opens with the company's Promise-Ledger line (reviewed ledgers only) and a link to the
  chain, the investor's own last meeting note on the company (synthetic, labelled, with date and
  who was there), and a drafted opener to the first person to call, with Copy opener and Copy
  questions. The opener is assembled from stored facts only (their name, when you last spoke, the
  filing's own one-line fact and date, where they actually worked); to a current employee it asks
  only for "what's public". Keep-warm nudges carry the same drafted opener. (`components/ActionBlock.tsx`,
  `network/service.py` `last_note` / `opener`, `for_item(fact=, when=)`.)
- **"Who can help?" on each research section** (owner item 4): Business, Bull vs bear and Financials
  carry the same button as the Promise ledger.

## 2026-11-14 — Compact Research summary (step 6)
- A new **20-second brief** sits above the Promise Ledger and uses only fields already present in
  the stored research report: the latest quarterly result, the ledger's computed pattern, the
  first resolved verdict in the report's existing order, the first stored ledger question, the
  top stored Who-can-help contact, calls read and review status. It performs no new scoring and
  writes no data.
- Result numbers link to the quarter's XBRL filing; the resolved verdict links to its existing
  chain. Missing results, verdicts, questions or contacts are stated plainly rather than filled.
  Synthetic contacts remain labelled synthetic.
- Promise chains are collapsed on a normal Research visit so the summary stays scannable. A
  results-card `?fy=` deep link still opens and scrolls to the requested chain.
- Phone evidence: `docs/screens/step6_research_summary_dark.png` and
  `docs/screens/step6_research_summary_light.png`.

## 2026-11-14 — Rules-first command bar with typed stored-data tools (step 7)
- One input is docked above the tab bar on every screen. Exact NSE symbols/company names route to
  Research, and "who do I know / who knows / who can help" routes into the existing People search,
  without a model. The bundled fallback catalog contains the companies already in FINN; the live
  catalog endpoint contains the stored NSE equity master.
- Only unmatched natural-language commands call Gemini. The model returns a validated plan of at
  most two calls from a closed enum: brief, filings, research section, Who can help, paths or price
  stats. It writes **zero answer sentences**. Code validates the symbol, reads existing stored
  views/tables, computes price changes, and returns typed blocks with sources. Research facts never
  enter the model prompt and never come from model knowledge.
- Limits follow the research-job pattern: salted client hash only (never raw IP or prompt), 10
  fallback commands/hour and 30/day per client, 200/day globally. Symbol and People rules remain
  available after a model limit or outage. Hosted calls use the existing free Gemini tier.
- Verified examples on the local Neon mirror with the configured hosted model: `CREDITACC` →
  Research; `Who do I know at HDFC Bank?` → populated People search; `Show TITAN's 7-day brief` →
  three NSE-linked brief items; `Show CREDITACC promises and who can help` → reviewed ledger block
  plus stored synthetic contacts. Screens: `docs/screens/step7_command_bar_dark.png`,
  `step7_command_bar_light.png`, `step7_command_result_dark.png`, `step7_rule_creditacc.png`,
  `step7_rule_people.png`.

## 2026-11-14 — Standards-based Web Push (step 8a)
- Proceeded with the browser Push API after checking the platform limits: iOS/iPadOS supports Web
  Push for Home Screen web apps from 16.4, permission must follow direct user interaction, and the
  same service-worker flow works on supported Android and desktop browsers. No paid provider is
  required, so a fallback channel was not built.
- Settings asks for permission only after **Enable alerts** is tapped and states the iPhone Home
  Screen requirement first. A subscribed device can send a rate-limited test alert. The regular
  push pipeline sends each new stored 24-hour Now card once per device; notification text comes
  from that stored card, and tapping it opens and highlights the exact card in the 7-day brief.
- Browser-issued endpoints and keys are stored server-side; raw IPs and notification text are not.
  The service fails closed when VAPID is absent. Render still needs `VAPID_PUBLIC_KEY` and
  `VAPID_PRIVATE_KEY`; no secret was generated, printed or committed.
- Evidence: `docs/screens/step8a_web_push_dark.png` and `step8a_web_push_light.png`. Tests cover
  subscription validation, stored-card payload/deep link, automatic delivery deduplication and URL
  construction.

## 2026-11-15 — Dismissible first-run guide (step 8b)
- A compact **Three things to try** card appears on Today until explicitly dismissed. Its actions
  are deterministic existing routes, not generated suggestions: the 7-day brief, CREDITACC's
  reviewed 20-second Research summary, and the existing People search populated for HDFC Bank.
- Dismissal is stored only in browser local storage. The Alert rules sheet is now titled Settings
  and includes **Show three things to try**, which clears the dismissal and closes the sheet so the
  card is immediately reachable again.
- Used a card instead of a modal so first run never blocks the investor's brief. Phone evidence:
  `docs/screens/step8b_first_run_dark.png` and `step8b_first_run_light.png`.

## 2026-11-15 — Pre-call brief with evidence cutoff (step 8c)
- No reviewed holding has a stored results or earnings-call date in the next seven days, so the
  card takes the required replay path. It reconstructs Larsen & Toubro **as of 30 Apr 2026**, five
  days before Q4 FY26 results were filed on 5 May. The replay cutoff is enforced in code: later
  guidance points and results filings cannot enter the card.
- The promise and run-rate are computed only from the reviewed report's stored evidence: 15% FY26
  revenue-growth guidance from the Q2 call; revenue from six XBRL filings gives +12.0% for 3Q YTD;
  reaching 15% required about +22.3% YoY in Q4. The live API result and bundled snapshot were
  compared byte-for-structure and matched.
- Three templated questions use only those values and link every transcript/XBRL used. Who-can-help
  links to the existing top LT contact, Ananya Mistry, labelled synthetic. Phone evidence:
  `docs/screens/step8c_pre_call_dark.png` and `step8c_pre_call_light.png`.

## 2026-11-15 — Two-sided filter audit (step 8d)
- Added a 30-day audit over the existing brief tiers and stored EOD prices. For each filing it
  observes the next two trading sessions and uses the investor's existing ±6% vs-NIFTY alert
  threshold. It changes no classification, scoring or alert rule.
- Current result: one buried item followed by a threshold move (CG Power ESOP paperwork, -6.3%
  vs NIFTY on 5 Nov) and three Now items followed by no threshold move in either session (Titan
  results, CG Power's court stay, Deepak Nitrite results). A Now item is not called quiet until two
  later sessions exist.
- The card says prominently: **a price move does not prove the filing caused it**. Filing links,
  dates, stock moves, NIFTY-relative moves and the Yahoo Finance/NSE credit remain visible. Phone
  evidence: `docs/screens/step8d_filter_audit_dark.png` and `step8d_filter_audit_light.png`.

## 2026-11-15 — Evidence-led mobile design pass (step 8e)
- Kept the existing information architecture and one Source Sans 3 face, but constrained the UI to
  three computed type sizes (metadata, reading text, titles). Bottom navigation now has labelled
  inline SVG icons; focus-visible outlines are consistent and all meaning still has a written label,
  so colour is never the only signal.
- Guidance ranges use accessible inline SVG geometry, while the existing Research trajectory keeps
  its SVG revenue bars and margin sparkline. Bottom sheets alone receive a short entrance transition,
  disabled under `prefers-reduced-motion`; ordinary cards do not animate.
- Fixed two screenshot findings without changing stored facts: CreditAccess no longer repeats its
  stored “single business segment” statement, and Who-can-help rankings now place former employees
  ahead of flagged current employees while preserving relevance order inside each group. A stale
  opener is hidden if it no longer addresses the displayed first call.
- Both themes retain the existing AA-tested tokens and explicit loading/error/empty copy. Directly
  comparable after shots are in `docs/screens/after/` (Today, CreditAccess and Settings, dark/light);
  the baseline remains in `docs/screens/before/`. Full gate: 92 API and 25 web tests, lint, types,
  production build and tracked-secret scan all green.

## 2026-11-15 — Live generalisation run (step 9, partial at queue limit)
- Selected symbols absent from the live Research index, not just the bundled snapshot. `SJS` is the
  small-cap case; `AUBANK` is the financial-company case; `DIXON` and `TITAN` broaden the sample.
- Three allowed jobs completed on GitHub runners: SJS job 4 in 139 s (12 quarters, 8 calls, 8
  guidance items), AUBANK job 5 in 177 s (12 / 8 / 10), and DIXON job 6 in 318 s (12 / 8 / 9).
  Each live report is correctly labelled generated automatically and **not reviewed**.
- The financial run exposed an honest coverage gap: AUBANK has 12 stored quarters but the compact
  summary says no quarterly result is stored, because its bank-format facts do not supply the
  result line that summary expects. No engine rule was changed to disguise this.
- TITAN reached the live queue but was rejected with HTTP 429: “3 new tickers an hour, 6 a day from
  one connection.” The client identity was not spoofed. Thus this checkpoint records three
  successful unseen runs and one admission failure, not four successes.
- Phone evidence: `docs/screens/step9_live_sjs_dark.png` and
  `docs/screens/step9_live_aubank_light.png`.

## 2026-11-15 — Final submission audit and Push activation fix
- Re-read the authoritative five-page challenge PDF; `docs/brief.pdf` is byte-identical to the
  owner's original. The actual deliverables are: deployed mobile prototype, **public** GitHub repo,
  AI build history and a short covering-email write-up. There is no separate form in the brief.
- Packaged five sanitized Claude Code/Codex text exports under `docs/build-log/` with an index of
  date, goal, outcome and a concrete model/tool correction. Tool outputs, hidden reasoning, system
  instructions and machine/account metadata are omitted. Known secret patterns are redacted and
  scanned; the reproducible exporter is `scripts/export_build_history.py`.
- Corrected stale public documentation that still said Web Push was absent. The covering note is
  690 words before its source notes, within the planned 500–700-word budget. Added
  `docs/SUBMISSION.md` with the exact recipient, subject, required links and send-time checks.
- The first Android subscription exposed a real race: `serviceWorker.register()` returned while
  the worker was installing, so `PushManager.subscribe()` saw no active worker. FINN now awaits
  `navigator.serviceWorker.ready`; the worker claims clients on activation, and a regression test
  locks the registration-before-ready order.
- Full local gate after starting the test database: 92 API and 26 web tests, lint, types, production
  build and tracked-secret scan all green. Full git-history secret scan: zero hits across 61 commits.
- Remaining release actions are intentionally human-controlled: make the repository public only
  after the final committed history scan, and confirm one real-device test alert after Vercel deploys.
