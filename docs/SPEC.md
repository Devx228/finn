# FINN — Build Specification for Coding Agents

**Challenge:** ENAM Holdings — Founding AI Engineer Build Challenge (FINN: Financial Investment Agent)
**Deadline:** 15 November 2026. Scheduling is owned by the human; this spec optimises for quality and gives a build *order*, not a timetable.
**Deliverables:** (1) mobile-first working prototype, deployed; (2) public GitHub repo; (3) AI build history; (4) short writeup in the covering email.
**Submission:** email to `assessment@enam.com`, subject exactly `IIT Kanpur – Founding AI Engineer - 2027`.

This document is the single source of truth for the build. If something here conflicts with the original brief (`docs/brief.pdf`), the brief wins — stop and flag it.

---

## 0. How to use this document (read first, agents)

1. Read sections 1–4 fully before writing code. They define what wins and what is out of scope.
2. Build in the phase order of section 16. Each phase ends in a **gate** — a thing that must demonstrably work before the next phase starts. Never start a phase with the previous gate red.
3. Priorities define **order, not ambition**: **P0** = the spine, built first; **P1** = what makes the submission stand out, and is intended to ship in full; **P2** = extras. The target is all of P0 and P1 working well. Never start a P1 item while a P0 gate is red, and never start P2 before P0 and P1 work on a phone.
4. Anything marked **VERIFY** is a fact that may have drifted (an endpoint shape, a free-tier limit, a model name). Check it against the live source before depending on it, and record what you found in `docs/DECISIONS.md`.
5. **Never fabricate data.** No invented filings, numbers, quotes, executives, or prices. Market data and filings are real. The investor's network is synthetic and must be labelled synthetic everywhere it appears.
6. **Numbers are computed in code, never by a model.** Models extract and explain; Python does arithmetic.
7. Keep `docs/DECISIONS.md` as an append-only log: date, decision, alternatives considered, why. This feeds the writeup and the build history, both of which are graded.
8. The companion file, *"Reference: Announcement Categories & Financial Glossary"*, lives at `docs/reference.pdf`. Read it before Phase 2. This spec already adopts its 17 announcement categories (section 8.1) and its definitions of Revenue / EBITDA / PBT / PAT / margin / QoQ / YoY. Use its vocabulary in the UI — the graders wrote it. The glossary also defines contingent liabilities, related-party transactions, auditor's qualification, pledging, D/E, FCF and ROCE/ROE; a firm defines the terms it cares about, so each of those appears somewhere in the product (sections 8.1, 10.4).
9. If blocked for more than 30 minutes on a data source, switch to the documented fallback and move on. A running demo beats a perfect scraper.

---

## 1. What the graders actually want

Extracted from the brief; every design choice below traces to one of these.

| # | What they said | What it means for the build |
|---|---|---|
| 1 | "How you build, what you choose to build, and the creativity and judgment behind it — not completeness or polish." | Fewer workflows, each with a visible point of view. Leave things out on purpose and say so. |
| 2 | "The scarce skill is not aggregating information. It's filtering it… burying everything else, beautifully." | The ranking engine and the *buried* pile are the product. Show what was hidden and why. |
| 3 | "The Network is not a separate app… woven into Push or Pull, not bolted on." | One consistent "Who can help?" affordance on every card and every research section. |
| 4 | "Show us what it notices that the investor wouldn't." | Network must produce non-obvious observations (coverage gaps, second-degree paths, the investor's own old notes contradicting a new filing). |
| 5 | "The difference between summarising management and analysing them — the kind of thing we value most." | The promised-vs-delivered ledger is the centrepiece of Pull. Spend the strongest model here. |
| 6 | "Ground it in the primary sources… don't lean on the model's own outside knowledge." | Closed-book prompts, page-level citations, a deterministic citation verifier. |
| 7 | "Build the engine to generalise… We may point it at a company you didn't pick." | A live research pipeline that works on any NSE symbol, with honest degradation when data is missing. |
| 8 | "No AI slop… core, concise, beautifully presented, and interactive. Density and design both count." | No paragraphs of generated prose. Typed cards, tables, verdict lines. A short text budget per component. |
| 9 | "A demo that doesn't run is the worst outcome." | Three layers of resilience (live → cached DB → bundled snapshot). No login wall. |
| 10 | "Efficiency earns bonus points… model routing, caching, chunking." | Rules before models, cheap model before strong model, content-hash cache, and a visible cost ledger. |
| 11 | "Make it easy for us to try on a phone." | Responsive web/PWA at a plain URL. Works in mobile Safari and Chrome without installing anything. |
| 12 | AI build history is a deliverable. | Preserve every agent session. Keep the decision log. Show course-corrections. |
| 13 | Writeup must cover pipelines, security & privacy, LLMs & agents, cloud, what was left out, what's next. | `docs/ARCHITECTURE.md` + a diagram, written as we build, not at the end. |

**Minimum bar for a valid submission:** Push, Pull and Network each have at least one workflow that works end-to-end on the deployed URL on a phone.

---

## 2. Product point of view

**FINN is a briefing, not a feed.** A feed is infinite and makes the investor do the filtering. A briefing is finite, ordered, and ends.

Every item FINN shows answers three questions, in this order, and nothing else:

1. **What changed?** — the fact, with its number.
2. **So what?** — one line on why it matters to *this* portfolio.
3. **Who can help?** — the person in the investor's own network best placed to explain it, and why them.

Design principles the whole build follows:

- **Finite.** The daily brief has an end: "You're caught up. 41 filings buried." The buried pile is one tap away, grouped by type, so the investor can audit FINN's judgment. Trust comes from showing what was hidden.
- **Structured, not chatty.** Answers are typed cards (table, people, path, ledger), never chat bubbles full of prose. Any generated sentence has a hard word budget.
- **Every claim is one tap from its source.** Filing PDF and page, transcript and page. No citation, no claim.
- **Numbers before words.** Tabular figures, deltas, basis points. Words only where a number can't say it.
- **The network appears at the moment it's useful**, attached to the event, with a reason. It is never a contact list.
- **Honest about uncertainty.** "Not disclosed in the sources" is a valid, visible answer. Unverified extractions are badged.
- **Compliance-aware.** A current employee of a listed company is a potential insider. FINN flags that and prefers former employees and adjacent-company contacts (see 9.6). A public-markets firm will notice this.

---

## 3. Scope

### P0 — must ship

**Push**
- Windowed digest (default 24h; 3d / 7d / 30d / custom) over all portfolio filings, in three tiers: **Now**, **Worth knowing**, **Buried**.
- Three rich card types: **Results** (Revenue / EBITDA / PBT / PAT with QoQ and YoY), **Management change** (bio of incoming person + network overlap), **Material event** (M&A / capex / litigation → best person to call, and why).
- One-line "so what" for other material types; everything else buried with counts.
- Triggered alerts with configurable thresholds: volume multiple vs recent average, price move ±X%, announcement categories I care about. In-app alert inbox.
- "Why is this here?" on every item (score breakdown).

**Pull**
- Research view for any NSE symbol with: Business snapshot, Financial snapshot, Trajectory, **Promise Ledger (narrative vs numbers)**, Guidance, Bull vs Bear. Each claim cited.
- Live pipeline with visible progress for a symbol not yet cached.

**Network**
- "Who can help?" sheet on Push cards and Research sections: ranked people, relationship path, reason, what they'd know, questions to ask.
- Second-degree paths with a link-strength score and evidence.
- Direct query: "who do I know at / who knows about X".
- Synthetic network of ~70 contacts overlapping portfolio and research companies.

**Platform**
- Deployed URL, no login, usable on a phone. Bundled snapshot fallback.
- Cost ledger screen. README. Architecture doc with diagram.

### P1 — the differentiators (intended to ship in full, after the P0 spine)
- Balance sheet and Cash quality research sections, and a **Red flags** section (auditor's qualification, contingent liabilities, related-party transactions, promoter pledging).
- Results card linked to the Promise Ledger ("guided 20–22% margin, delivered 19.1%").
- Ask bar: natural-language command that routes to typed cards (tool-calling agent).
- People tab: expertise map, **coverage gaps** (portfolio weight vs network depth), keep-warm nudges with a drafted opener.
- Person dossier (pre-meeting diligence).
- Note resurfacing: the investor's own past meeting notes shown against a new filing.
- Web Push notifications (PWA). Swipe feedback that adjusts ranking.
- Unexplained-move detection (price/volume anomaly with no filing nearby).
- Classifier eval harness with a labelled set.

### P2 — stretch
- Telegram bot as a second push channel. Voice input on the Ask bar. Spoken 60-second morning brief (browser speech synthesis). Supplier/customer extraction from annual reports. Local small model for bulk classification.

### Deliberately out of scope (say so in the writeup)
- Real LinkedIn data or any scraping of profile sites. Real-time/intraday prices. Trading, portfolio P&L, valuation models. Broker notes, news, or any secondary research. Multi-user auth (designed for, not built). Native app builds.

---

## 4. Demo data choices

### 4.1 Portfolio (15–20 NSE names)

Do not hardcode from memory. Build `scripts/pick_portfolio.py`:

1. Start from the candidate pool below (**VERIFY** each symbol against the NSE symbol master; drop any that fail).
2. For each candidate, pull the last 90 days of filings and tag them with a minimal headline tagger (the full rules classifier of section 8.1 is built in Phase 2). *[Changed 2026-11-12: was a wrong reference to 7.2; see DECISIONS.md.]*
3. Score "demo richness": has a results filing in the last 30 days; has a real management change (CFO / MD / CEO / KMP) in 90 days; has a real M&A, large capex, or litigation filing in 90 days.
4. Choose 18 names maximising sector and size diversity subject to: ≥ 2 companies with a real management change, ≥ 3 with a real material event, ≥ 12 with a recent results filing, ≥ 1 bank, ≥ 1 NBFC, ≥ 2 small/mid caps.
5. Write the choice and the reasons to `data/portfolio.json` and `docs/DECISIONS.md`.

Candidate pool (cover the themes the brief names — specialty chemicals, rural lending, semiconductors — so the expertise-map demo lines up with their examples):

| Sector / theme | Candidates |
|---|---|
| Banks | HDFCBANK, ICICIBANK, AUBANK, IDFCFIRSTB |
| NBFC / rural lending | BAJFINANCE, CHOLAFIN, CREDITACC, MMFIN |
| IT services | INFY, HCLTECH, PERSISTENT, KPITTECH |
| Specialty chemicals | SRF, AARTIIND, DEEPAKNTR, PIIND, NAVINFLUOR |
| Semiconductors / electronics | DIXON, KAYNES, CGPOWER, TATAELXSI |
| Consumer | HINDUNILVR, TITAN, TRENT, DMART, VBL |
| Pharma / healthcare | SUNPHARMA, DIVISLAB, APOLLOHOSP |
| Industrials / infra | LT, POLYCAB, ULTRACEMCO, SUZLON |
| Energy / conglomerate / telecom | RELIANCE, BHARTIARTL, TATASTEEL |
| Autos | MARUTI, M&M, EICHERMOT |

Each holding gets a mock weight (%) and a mock entry date. Weight feeds ranking.

### 4.2 Research demo set (3–5, may be outside the portfolio)

Pick for what they prove:

- **One company that gives explicit numeric guidance every quarter** (a large IT services name that publishes a revenue-growth band and margin band is ideal) — this is the hero for the Promise Ledger.
  *[Changed 2026-11-13 by the owner: hero = **KAYNES** (rupee revenue, growth and EBITDA-margin
  guidance checkable straight from filings); second = **CREDITACC** (loan growth, credit cost,
  ROA, ROE); INFY stays on 4 of 8 calls as the example of guidance cuts and constant-currency
  handling.]*
- **One mid-cap with capex / capacity guidance** — shows multi-year promises.
- **One bank or NBFC** — proves the engine handles financials (no EBITDA; different statement rows).
- **One small cap with few or no concalls** — proves graceful degradation ("annual-report-only mode").

### 4.3 The investor and the mock network

The investor is a fictional persona defined in `data/investor.json`: two alma maters, three past employers (e.g., a brokerage research desk, a bank, a fund), cities, and the sectors they cover. What the investor "gives FINN" as a starting point, stated in the UI onboarding copy and the writeup:

1. A contacts export (the format of a professional-network connections export: name, company, position, connected-on).
2. A meeting log for the last 2–3 years: date, company, people met, free-text notes.
3. Their own CV (alma maters, employers, years).

Network rules:
- ~70 contacts, **all fictional names**, `is_synthetic = true`. Real organisations as employers are fine; real private individuals are not.
- Real executives who appear in filings are stored separately as **public figures**, with career facts taken only from the filing or annual report that names them, and a source URL.
- Overlap is engineered after ingestion (`scripts/seed_overlaps.py`): once filings have yielded real executives and their career histories, plant synthetic contacts whose tenures overlap those histories (same employer, overlapping years, plausible function), plus alumni overlaps with the investor.
- Coverage targets: every portfolio company has ≥ 1 relevant contact, *except two holdings left deliberately uncovered* so the coverage-gap insight has something to show. Each research company has ≥ 2. At least 6 contacts are "cold" (last contact > 9 months) with a former employer in the portfolio, to power keep-warm nudges.
- ~40 meeting-log entries with notes; at least 3 notes written so that a real recent filing confirms or contradicts them (for note resurfacing).
- Deterministic generation with a fixed seed; commit the output JSON.

---

## 5. Architecture

### 5.1 Decision summary

| Concern | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind, PWA, on Vercel | Fast to ship, plain URL on a phone, installable, edge-cached reads. |
| Backend | One Python FastAPI service | yfinance, PDF tooling and the pipeline are Python; one home for all logic. |
| Backend host | Render free web service (Docker) with an external keep-alive pinger. *[Changed 2026-11-12: zero spend. Cloud Run needs billing; Hugging Face Docker Spaces now need PRO; Koyeb needs a card. See DECISIONS.md.]* | Cold start is the main demo risk; keep-alive + snapshot fallback cover it. |
| Database | Postgres (Neon free tier preferred — wakes on connect). **VERIFY**. | One store; JSONB for view-models; `tsvector` for page-level search. No vector DB. |
| Scheduler | Ingest CLI on the owner's laptop (local Ollama is the BULK tier). GitHub Actions: CI, keep-alive, and a rules-only filings + alerts job (NSE answers GitHub runners, verified 2026-11-12). *[Changed 2026-11-12.]* | Zero spend; model enrichment needs the local GPU. |
| Object storage | PDFs are not stored; keep URL + content hash + extracted page text in Postgres | Minimal footprint; text is what we need. |
| LLM access | Provider-agnostic router with three tiers (section 6) | Free-tier limits move; no step may be tied to one vendor. |
| Push channel | In-app inbox (P0), Web Push via VAPID (P1), Telegram bot (P2) | iOS only delivers web push to a home-screen-installed PWA, so in-app must stand alone. |

### 5.2 Shape

```
                      GitHub Actions (cron)                    Phone (PWA)
                             │                                      │
                      ingest CLI (Python)                    Next.js on Vercel
   Yahoo ─ prices ──►  ┌────────────────────┐              (UI + cached GET proxy
   NSE ─ filings ─────►│ fetch → parse →    │               + bundled snapshot)
   NSE ─ XBRL results ►│ classify → extract │                       │
   AR / transcripts ──►│ → link → score →   │                       ▼
   Synthetic network ─►│ materialise views  │──► Postgres ◄── FastAPI (read API,
                       └─────────┬──────────┘   (raw + views)  live research job,
                                 │                              network queries,
                          LLM router (cheap → strong)           ask agent, alerts)
                          + content-hash cache + cost ledger
```

**Key idea: the pipeline materialises view-models.** Ingestion writes finished, render-ready JSON documents (`brief_items`, `research_reports`, `person_dossiers`). The read path is a `SELECT`. Nothing the grader sees on first load waits on a model call.

### 5.3 Three layers of resilience

1. **Live:** frontend → Vercel route handler → FastAPI → Postgres.
2. **Cached:** Vercel caches GET responses (`revalidate` 5–15 min, stale-while-revalidate).
3. **Snapshot:** `web/public/snapshot/*.json` is exported from the DB by `scripts/export_snapshot.py` and committed. If the API errors or exceeds 4 s, the UI renders the snapshot with a small "Snapshot · as of {date}" badge.

On app load the frontend fires a non-blocking `GET /health` to warm the backend.

### 5.4 Repository layout

```
finn/
  README.md
  docs/  brief.pdf  reference.pdf  SPEC.md (this file)  ARCHITECTURE.md  DECISIONS.md
         WRITEUP.md  diagram.svg  build-log/  evals.md
  api/
    pyproject.toml  Dockerfile
    finn/
      config.py  db.py  models.py
      sources/   base.py  prices.py  nse.py  pdf.py  symbols.py
      llm/       router.py  cache.py  ledger.py  prompts/
      push/      classify_rules.py  classify_llm.py  bundle.py  results.py
                 mgmt_change.py  material_event.py  score.py  alerts.py  digest.py
      pull/      financials.py  transcripts.py  annual_report.py  ledger.py
                 sections.py  verify.py  pipeline.py
      network/   graph.py  resolve.py  strength.py  who.py  paths.py
                 insights.py  dossier.py
      ask/       agent.py  tools.py  blocks.py
      api/       main.py  routes_*.py
      cli.py
    tests/
  web/
    app/  components/  lib/  public/snapshot/  public/manifest.json  public/sw.js
  data/  portfolio.json  research_set.json  investor.json  network.json
         meetings.json  orgs_seed.json  value_chain_seed.json  eval/labelled.jsonl
  scripts/  pick_portfolio.py  gen_network.py  seed_overlaps.py  export_snapshot.py
  .github/workflows/  ingest.yml  keepalive.yml  ci.yml
```

---

## 6. LLM strategy, routing and cost

### 6.1 Tiers, not model names

Configure by environment; never hardcode a model in business logic.

| Tier | Used for | Requirements | Suggested default (**VERIFY** at build time) |
|---|---|---|---|
| `RULES` | ~80% of filing classification, all arithmetic, all scoring, all network ranking | No model | — |
| `BULK` | Ambiguous-filing classification (batched), transcript claim extraction, executive-bio extraction, results-table extraction, annual-report section extraction | Cheap, large context, accepts PDF or long text, JSON output | A "Flash-Lite"-class model on a free tier |
| `REASON` | Promise Ledger resolution, narrative-vs-numbers verdicts, bull/bear, ask-agent planning | Strongest available; low call volume | The best free-tier "Flash"-class model. *[Changed 2026-11-12: no paid fallback.]* |
| `VISION` | Scanned results PDFs only | Reads images/PDF pages | Same provider as BULK if multimodal |

Free-tier facts to plan around (all **VERIFY** — providers no longer publish stable tables; read the live quota in each provider's console):
- Daily request caps on free tiers can be very low for the stronger models (tens of requests/day) and a few hundred/day for the lite models. **Design for ~20 strong calls and ~400 bulk calls per day.**
- Some fast-inference free tiers cap tokens per minute so low that a 20k-token transcript won't fit in one request; use those only for short classification prompts.
- Free tiers may use prompts to improve the provider's products. Acceptable here because filings are public and the network is synthetic. In production, personal data goes only to a paid, no-training endpoint (section 12).

Router behaviour (`llm/router.py`): ordered provider list per tier; on 429 or 5xx, exponential backoff then fall to the next provider; per-provider token bucket honouring RPM/TPM/RPD from config; strict JSON-schema output with one repair retry; every call logged to `llm_calls`.

### 6.2 Efficiency techniques (all P0 — this is graded)

1. **Rules first.** Exchange category + headline regex decides most filings at zero cost.
2. **Batching.** Classify ambiguous filings 10 per call.
3. **Content-hash cache.** Key = `sha256(model_tier + prompt_version + input_hash)`. A document is never read by a model twice. Transcripts and annual reports are immutable — their extractions are cached forever.
4. **Read less.** Results filings: locate the statement page by text search and send only those 1–3 pages. Annual reports: route to MD&A / segment / business pages by table-of-contents and keyword scoring; never send 300 pages.
5. **Map cheap, reduce strong.** Per-transcript claim extraction on BULK; one REASON call per company over the compact claims JSON plus computed actuals.
6. **Compute, don't generate.** Deltas, margins, ratios, verdicts on numeric claims, link strengths, rankings — all code.
7. **Lazy depth.** Deep reads only for items that reach the *Now* tier.
8. **Materialised views.** The read path makes zero model calls.

### 6.3 Cost ledger

Table `llm_calls(id, ts, tier, provider, model, purpose, input_tokens, output_tokens, cache_hit, latency_ms, list_price_usd)`. `list_price_usd` is what the call *would* cost at paid list price (from a config table), so the ledger is meaningful even on free tiers.

Expose `/api/cost` and a small "Under the hood" screen: e.g. *"This week: 1,284 filings → 1,031 decided by rules · 253 by bulk model in 26 calls · 14 deep reads. 91% cache hit. List-price cost ₹X."* Plain numbers, no decoration.

---

## 7. Data pipelines

General rules for every source: polite rate (≤ 1 request/second per host, jittered), browser-like headers, retries with backoff, on-disk/DB caching, and a recorded fallback. Fetching happens in the ingest job, not in the request path — except the live research job.

### 7.1 Symbols and identity (`sources/symbols.py`)

- NSE symbol master: the public equity list CSV on NSE archives (`EQUITY_L.csv`) → symbol, company name, ISIN. **VERIFY** URL.
- Yahoo ticker = `{SYMBOL}.NS`. *[Changed 2026-11-12: no BSE codes needed.]*
- `companies(id, nse_symbol, isin, name, aliases[], sector, industry, is_financial, mcap_bucket)`.
- `is_financial` (bank / NBFC / insurer) is derived from industry and switches the metric set everywhere.

### 7.2 Prices and volume (`sources/prices.py`)

- `yfinance`, one batched `download` for all tickers, daily bars, ~1 year history. Also pull a NIFTY 50 index series for abnormal-return calculation.
- Yahoo rate-limits shared cloud IPs. Run this from the scheduled job; on failure keep the last good data and mark `stale_since`. Never call Yahoo from a user request.
- `prices(company_id, date, open, high, low, close, adj_close, volume)`.
- Derived per day: `ret_1d`, `abn_ret_1d = ret_1d − nifty_ret_1d`, `vol_multiple = volume / mean(volume, prior 20 sessions)`, 52-week high/low flags.

### 7.3 Corporate announcements (`sources/nse.py`, behind `sources/base.py`)

*[Changed 2026-11-12: NSE is the single source. BSE's API returns 403 to our clients and was not
worked around; Screener's terms forbid copying and public display. See DECISIONS.md.]*

**Adapter interface.** `sources/base.py` defines `FilingsSource` (announcements for a symbol and
date range; the incremental feed), `FundamentalsSource` (annual-report list, transcripts,
structured results) and `DocumentFetcher` (download once by URL, return bytes + sha256). NSE is
the only implementation; another exchange or a licensed feed can be added without touching
callers.

**Access rules (owner decision, mandatory; DECISIONS.md 2026-11-12).** One request at a time, at
least 1 s apart, shared by every NSE caller in the process. Every response cached; a document
URL is never fetched twice. Only portfolio and research companies plus on-demand tickers. On a
403, 429 or bot challenge: stop, record it, surface "source refused" — never retry around it.
PDFs are not re-hosted: we keep extracted text and link to the NSE original. NSE is credited in
the UI.

Endpoints (verified 2026-11-12, plain requests, no cookies):
- Announcements: `https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=…&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`. Fields: `an_dt`, `desc` (exchange category), `attchmntText` (subject), `attchmntFile` (PDF on `nsearchives.nseindia.com`), `attFileSize`, `sm_isin`, `seq_id`, `hasXbrl`. A two-year range returns in one response.
- Incremental feed: `https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml` (rolling ~1 day, all companies; filter to our symbols).

Reachability: answers the owner's laptop and GitHub-hosted runners; **refuses Render (403)**.
So the server never calls NSE; ingest runs on the laptop, and the optional cloud alert job runs
on GitHub Actions.

Storage: `filings(id, company_id, exchange, exch_id, ts_ist, headline, subject, exch_category,
pdf_url, pdf_sha256, n_pages, text_pages jsonb, is_scanned, dup_of, bundle_id)`.

PDF handling (`sources/pdf.py`): download once, hash, extract text per page with PyMuPDF. If the
text layer is near-empty, mark `is_scanned` and defer to the VISION tier only if the item needs
a deep read.

Backfill 120 days for every portfolio company on first run; thereafter incremental.

### 7.4 Fundamentals (`sources/nse.py`)

*[Changed 2026-11-12: Screener dropped; every number now comes from exchange filings.]*

- **Structured results — the numeric spine, parsed by code, no model.**
  - Up to Dec 2024: `/api/corporates-financial-results?index=equities&symbol=…&period=Quarterly`
    lists every results filing (consolidated/standalone, audited, period, `bank` flag N/B/F)
    with an `xbrl` XML link. Depth seen: 9–80 quarters (RELIANCE/INFY standalone from 2005;
    KAYNES from listing in 2022).
  - From Mar 2025 (SEBI Integrated Filing): `/api/integrated-filing-results?index=equities&symbol=…&type=Integrated Filing- Financials`
    with an `ixbrl` link to an HTML rendering of the XBRL — label/value tables for P&L,
    balance sheet, cash flow, segments, notes and the auditor-opinion declaration.
  - Half-year filings (Q2, Q4) carry the balance sheet and cash flow; Q4 carries full-year
    figures. Unit is stated in the filing ("Level of rounding": lakhs/crores/millions).
- **Annual reports**: `/api/annual-reports?index=equities&symbol=…` → PDF per financial year.
  Used for business/segment description, MD&A, auditor's report, contingent liabilities and
  related-party notes (routed pages only), and to fill any year the structured data lacks.
- **Transcripts**: announcements whose `attchmntText` names a transcript (category "Analysts/
  Institutional Investor Meet/Con. Call Updates"). Coverage checked: 8 of the last 8 quarters
  for RELIANCE, INFY, PERSISTENT, KAYNES, CREDITACC, NAVINFLUOR, all as full-text PDFs.
- Banks (`bank=B`) file a bank format (interest earned, operating profit before provisions,
  NPA %, CET1, deposits); NBFCs (`bank=F` in older filings) use the Ind AS format with
  revenue from operations and finance costs. Map labels through an alias table per format;
  never assume a row exists.

Storage: `documents(id, company_id, kind[annual_report|transcript|results|presentation], period,
url, sha256, n_pages, pages jsonb, fetched_at)`, `doc_pages(doc_id, page_no, text, tsv
tsvector)`, `fin_quarterly(company_id, period_end, metric, value, unit, basis, source_url)`,
`fin_annual(...)`.

Period notation everywhere: Indian fiscal year, April–March. `Q2 FY27` = July–September 2026.
Store `period_end` dates; format for display.

### 7.5 Network profiles

Synthetic, generated by `scripts/gen_network.py` + `scripts/seed_overlaps.py` (section 4.3). Schema in section 9.1. Public-figure records come from filings (section 8.4).

### 7.6 Linking and entity resolution (`network/resolve.py`)

This is the "matching a name in a filing to a person in the network" question the writeup must answer.

**Organisations.** `orgs(id, canonical_name, aliases[], company_id nullable, industry, kind)`. Normalise (lowercase; strip Ltd / Limited / Pvt / Inc / India / punctuation), then: exact alias match → fuzzy match (rapidfuzz token-set ratio ≥ 92) → otherwise create a new org flagged `unreviewed`. Seed `data/orgs_seed.json` with aliases for every portfolio and research company and the employers used in the synthetic network (e.g. short names and former names).

**People.** A filing names a person; candidates are public figures and contacts. Score = name similarity (handle initials, name order, honorifics) combined with corroboration: shared organisation with overlapping years, matching role family, matching education. Thresholds: ≥ 0.9 same person; 0.6–0.9 shown as "possible match" and never merged automatically; < 0.6 distinct. Store `match_confidence` and the evidence. A name alone is never sufficient.

**Company relationships.** `org_relations(a, b, kind[peer|supplier|customer|parent|subsidiary], source, confidence)`. Peers come from shared industry classification (generalises to any ticker). Supplier/customer links come from `data/value_chain_seed.json` for the demo themes; extraction from annual reports is P2.

### 7.7 Schedules

| Job | Cadence | Notes |
|---|---|---|
| `finn ingest filings` | Every 30 min, 08:00–21:00 IST, weekdays | Incremental; runs classify → bundle → enrich → score → materialise → alert check. |
| `finn ingest prices` | 18:30 IST weekdays | Then run price/volume alert evaluation. |
| `finn ingest fundamentals` | Daily 06:00 IST | Only companies whose document list changed. |
| `finn materialise` | After each ingest | Rebuild `brief_items`, dossiers. |
| `finn export-snapshot` | Manual before submission, and nightly | Commits snapshot JSON. |
| keep-alive | Every few hours | Pings API and DB so nothing is asleep when a grader opens the link. |

GitHub cron is best-effort; that is fine for a prototype. "The moment something crosses a threshold" is honoured as "on the next ingest tick"; say so in the writeup and describe the production version (exchange feed / websocket + queue).

---

## 8. Push

### 8.1 Classification (`push/classify_rules.py`, `push/classify_llm.py`)

**Taxonomy: adopt the reference file's 17 categories as the top level, unchanged in name and meaning.** They are the labels shown in the UI and used in alert settings.

| Category | Contents per the reference | Default treatment | Sub-types FINN adds (the judgment) |
|---|---|---|---|
| `results` | Results, the board meeting approving them, decks, shareholder letters, publication ads | Bundle into one Results card → *Now* | `results_filing` (card), `board_meeting_notice` (date goes to an "upcoming" strip, otherwise buried), `deck`, `newspaper_ad` (always buried inside the bundle) |
| `M&A` | Acquisition, merger, demerger, JV, investing in or selling a subsidiary stake | Material-event card; tier by relative size | `routine_subsidiary_infusion` (small capital into a wholly-owned subsidiary → *Worth knowing* or buried by size) |
| `fund_raise` | Rights, QIP, preferential allotment, buybacks, debt such as commercial paper | *Now* for equity raises and buybacks; | `equity_raise`, `buyback`, `routine_debt` (CP/NCD roll-overs for lenders and large issuers → buried) |
| `management_change` | CEO, CFO, MD or director joining, resigning, retiring | Management-change card | `kmp_change` (CEO/MD/CFO → *Now*), `independent_director_rotation` (→ *Worth knowing*), `re-appointment` (→ buried) |
| `litigation` | Lawsuits, regulatory orders, fines, warnings, insolvency/restructuring | Material-event card; tier by amount relative to PAT/net worth | `small_penalty` (trivial tax/GST demands → buried, but counted) |
| `insider_trading` | Promoter/insider buying or selling own shares | *Worth knowing*; *Now* when large relative to holding or clustered | direction, % of holding, cluster of several insiders in 30 days |
| `earnings_call` | Call notice, transcript, recording link | Notice → upcoming strip; transcript → triggers the Promise Ledger refresh and a one-line "new call read" item | — |
| `investor_meetings` | One-on-one/group meetings, conferences | Buried | — |
| `credit_rating` | Assign, upgrade, downgrade, reaffirm | Upgrade/downgrade/outlook change → *Now* or *Worth knowing*; reaffirmation → buried | `action` extracted |
| `dividend` | Cash dividend with record date | *Worth knowing* one-liner with amount and record date | special dividends flagged |
| `bonus_split` | Bonus issue or split | *Worth knowing* | — |
| `capex` | New plant, facility, capacity expansion | Material-event card; tier by size relative to gross block / revenue | — |
| `press_release` | Order wins, products, partnerships, rumour clarifications | LLM-scored; order wins by size relative to revenue; **rumour clarifications are promoted** | `order_win`, `rumour_clarification`, `product_partnership` |
| `postal_ballot` | Notice and result | Buried, unless the resolution is itself material (then it inherits that category) | — |
| `agm_egm` | Notice and result | Buried, same exception | — |
| `pledging` | Promoter pledge created, released, changed | *Worth knowing*; *Now* when pledge rises materially | % of promoter holding pledged, direction |
| `unclassified` | Routine paperwork — ESOP allotments, compliance certificates, ESG reports, auditor appointments | Buried | **One deliberate exception: `auditor_resignation` or a qualified/modified audit opinion is promoted to *Now*.** The reference files auditor appointments here as routine, and they are; an auditor *leaving* mid-term or qualifying the accounts is not. Call this out in the writeup as a judgment call. |

A filing gets exactly one category and optionally one sub-type. Base scores per category/sub-type live in config (`push/score.py`).

Stage 1 — rules. Map exchange category/subcategory and headline patterns to a class and a base tier. Examples of **buried by rule**: trading-window closure; loss/duplicate share certificates; newspaper publication copies; Reg 74(5) certificates; ESOP allotments below a size threshold; analyst-meet schedule intimations; investor-grievance statements; closure of register. Examples of **promoted by rule**: financial results; change in directors/KMP; acquisition/scheme of arrangement; credit-rating change; resignation of statutory auditor.

Insider trades and pledging arrive as structured disclosures (SAST / PIT forms). Extract quantity, direction and resulting holding; compute in code the change as a % of the person's holding and of total equity, and the 30-day cluster count. A one-liner like "Promoter pledged a further 3.1% — 22% of promoter holding now pledged" is worth more than the filing title.

Stage 2 — BULK model, only for filings the rules cannot place (typically generic "Reg 30 / General updates"). Input per filing: headline, subject, first ~1,500 characters of text. Batched 10 per call. Output per filing: `{category, sub_type, materiality 0–100, one_line (≤ 18 words), entities: {people[], orgs[], amounts[]}, needs_deep_read}`.

### 8.2 Bundling and de-duplication (`push/bundle.py`)

- Same company + same PDF hash, or near-identical headline within 60 minutes across exchanges → duplicates; keep one.
- Results day produces several filings (results, press release, investor presentation, concall intimation, newspaper ad). Group filings of the same company within a 36-hour window that belong to the results family into **one bundle** rendered as one card with attachments. Same idea for a deal announcement and its follow-ups.

This is a real filtering win: five filings become one card.

### 8.3 Results card (`push/results.py`)

Goal: headline numbers from the **actual results filing**.

1. Find the statement page(s): search page text for markers such as "Statement of … Financial Results", "Revenue from operations", "Profit before tax", "Quarter ended". Prefer the **consolidated** statement when both exist.
2. *[Changed 2026-11-12]* First read the filing's structured XBRL / integrated-filing table (code, no model). Only if it is missing or fails validation, send the located pages to BULK (VISION if scanned) with a strict schema. The SEBI results format has columns for the current quarter, the preceding quarter and the corresponding quarter of the previous year — so **QoQ and YoY both come from this one document**.
3. Extract line items as reported: revenue from operations, other income, total expenses, finance costs, depreciation & amortisation, exceptional items, profit before tax, tax, profit after tax (and attributable to owners if shown), the unit (lakhs / crores / millions), basis (consolidated / standalone), audited/unaudited.
4. Compute in code, normalised to ₹ crore:
   - **Revenue** = revenue from operations.
   - **EBITDA** = profit before exceptional items and tax + finance costs + depreciation & amortisation − other income. The reference defines EBITDA as earnings before interest, tax, depreciation and amortisation, "a rough proxy for operating profitability"; Indian results statements do not print it, so it is derived. Excluding other income keeps it a measure of the core business. State the exact formula in the card's info sheet, and if the company's own press release reports an EBITDA figure, show it alongside when it differs by more than 2%.
   - **PBT** = as reported; if exceptional items exist, show both and flag it.
   - **PAT** = profit for the period.
   - QoQ % and YoY % for each; EBITDA and PAT margins with change in basis points.
5. **Financials** (banks/NBFCs): EBITDA is not meaningful. Show Net Interest Income / total income, pre-provision operating profit, PBT, PAT, and label the row accordingly. Do not force the four-row template onto a bank.
6. Validate: internal arithmetic (revenue + other income − expenses ≈ PBT within tolerance); unit sanity vs prior quarter; cross-check current-quarter values against `fin_quarterly` when present. Badge the card `verified` or `unverified — check filing`. Never silently show a number that failed validation.
7. One-line take, generated from the computed numbers only (≤ 20 words), e.g. "Revenue +14% YoY but EBITDA margin down 180 bps; PAT flat."
8. P1: attach the guidance check from the Promise Ledger when the company has one.

### 8.4 Management-change card (`push/mgmt_change.py`)

Insight to exploit: under the listing regulations, an appointment disclosure includes a **brief profile** of the appointee. So the bio comes from the filing itself (and the annual report if they're an internal promotion). No profile-site scraping needed.

1. BULK extraction from the filing: `{event[appointment|resignation|cessation|re-designation], role, person_name, effective_date, reason_given, outgoing_person, profile: {education[{institution, degree, year?}], career[{org, role, from?, to?}], years_experience, age?}}` with page citations.
2. Create/resolve the public-figure record (section 7.6).
3. Run network overlap (section 9.3): who worked at the same organisation in overlapping years, who studied at the same institution in overlapping years, and the best one-hop path.
4. Card content: role and effective date; 3-line bio in facts ("22 yrs · ex-{Org A} (2011–19), {Org B} (2019–26) · CA"); outgoing person and stated reason; **network strip** ("{Contact} overlapped with her at {Org A}, 2014–18 — finance. Strength: strong."). If there is no overlap, say "No one in your network overlaps" and show the nearest adjacent contact.
5. Resignations get their own judgment: flag clusters (e.g. second senior exit in 12 months; auditor or CFO exit close to results).

### 8.5 Material-event card (`push/material_event.py`)

For `M&A`, `capex`, `litigation` (and large `fund_raise` / `order_win`): *[Changed 2026-11-12: use the reference's category names.]*

1. Deep-read extraction (BULK): what, counterparty, amount, timeline, funding, and **size relative to the company** computed in code (amount ÷ trailing revenue or market cap). Relative size drives materiality — a ₹200 cr capex is noise for one company and a bet-the-firm move for another.
2. Pick the best person via the who-to-call engine (section 9.4), with **function fit** by event type: capex → operations / projects / finance; litigation → legal / compliance / the regulator's domain; M&A → strategy / someone who worked at the target or counterparty.
3. Card: the fact with numbers; the one-line so-what; **"Call {name}"** with one sentence of why and what they'd know; three specific questions.

### 8.6 Scoring and tiers (`push/score.py`)

Deterministic and explainable. Each component is stored so the UI can show "Why is this here?".

```
score = base[class]                       # 0–60, from config
      + magnitude                         # 0–20: relative size, surprise vs trend, CRITICALNEWS flag
      + portfolio                         # 0–10: holding weight
      + network                           # 0–10: a strong relevant contact exists
      + price_reaction                    # 0–10: |abnormal return| or volume multiple on the day
      + user_pref[class]                  # −20…+20: settings and swipe feedback
      − staleness                         # decays with age inside the window
```

Tiers: **Now** (score ≥ 70, hard cap of 5 items — if more qualify, the cap forces a choice and the rest fall to *Worth knowing*), **Worth knowing** (40–69, one-liners), **Buried** (< 40, grouped by class with counts). Thresholds live in config.

The digest for a window is `brief_items` filtered by time and sorted by score; the header states totals: "212 filings · 4 need you · 17 worth knowing · 191 buried".

### 8.7 Alerts (`push/alerts.py`)

`alert_rules(id, kind, params jsonb, scope[all|company_ids], enabled)` with defaults the user can edit:

- `volume_spike`: `vol_multiple ≥ 2.0` vs 20-session average (multiple and lookback configurable).
- `price_move`: `|ret_1d| ≥ 5%` (configurable), with a toggle "relative to NIFTY" that uses abnormal return so a market-wide day doesn't fire 18 alerts.
- `announcement_class`: per-class toggles (results, M&A, management change, auditor change, rating, litigation, fund raise…).
- P1 `unexplained_move`: a price/volume alert with no filing from that company in the surrounding 2 sessions. These are the interesting ones — surface them as "moved with no disclosure".

Evaluation is idempotent (`alerts_fired` unique on rule + company + date/filing). Each fired alert links to the related card and carries context: the triggering number, the threshold, and what else happened that day.

Delivery: in-app inbox with unread badge (P0); Web Push (P1) — service worker + VAPID keys + `pywebpush`; request permission only from a button tap; on iOS, show a one-line hint that notifications need "Add to Home Screen". Settings include a **"Send test alert"** button so a grader can see a push arrive.

### 8.8 Demo robustness for Push

- Window picker presets plus custom range.
- An unobtrusive **"as of" control** in settings (replay the brief as of a past date/time) so the richest real day in the last 90 days can be shown regardless of when the grader opens the app. Default is real "now". Mid-November is results season, so the default window should be rich anyway.

---

## 9. Network

### 9.1 Data model

```
persons(id, tenant_id, kind[contact|public_figure|investor], full_name, name_norm,
        headline, city, is_synthetic, source, source_url, created_at, refreshed_at)
employments(person_id, org_id, title, function, seniority 1–5, start_ym, end_ym nullable)
educations(person_id, institution_org_id, degree, field, start_y, end_y)
relationships(tenant_id, contact_id, how_known[ex-colleague|classmate|met-as-management|
              industry-friend|personal|introduced-by], since_ym, last_contact_date,
              interactions_24m, closeness 1–5, notes)
meetings(tenant_id, date, company_id nullable, person_ids[], notes, tags[])
expertise(person_id, theme, score, evidence)
```

`function` ∈ finance, operations, sales, strategy, legal-compliance, R&D-technical, treasury-credit, IR, HR, general-management. `tenant_id` is on every network table from day one.

### 9.2 Link strength (`network/strength.py`) — deterministic, explainable

**Investor ↔ contact (warmth)**, 0–1:
`0.35·closeness + 0.30·recency(last_contact, half-life 9 months) + 0.20·min(interactions_24m, 8)/8 + 0.15·tenure_of_relationship(capped at 10y)`

**Person ↔ person (overlap)**, 0–1, from shared history:
- Same organisation, overlapping months `m`: `min(m, 48)/48`, × 1.0 if same function, 0.6 otherwise, × seniority-proximity factor, × organisation-size discount (overlapping at a 200-person firm means more than at a 200,000-person one).
- Same institution with overlapping years: 0.5 if same programme and overlapping cohort window, 0.25 otherwise.
- Take the maximum across evidence items and keep all evidence for display.

Labels: ≥ 0.66 strong, 0.33–0.66 medium, else weak. Always show the evidence sentence, never the bare number alone.

### 9.3 Second-degree reach (`network/paths.py`)

For a target person T: for every contact C, `path_score = warmth(investor, C) × overlap(C, T)`. Return top paths with evidence: "You → {C} (ex-colleague, last spoke Mar 2026) → {T}: overlapped at {Org}, 2014–18, both in finance. Path: strong × medium." Render as a three-node path, not a graph hairball.

### 9.4 Who should I call (`network/who.py`)

Inputs: a company, a sector/theme, or an event. Candidate contacts get:

```
relevance = position_fit      # worked at the company 1.0 · competitor 0.7 · supplier/customer 0.7
                              # · same industry 0.4
          × recency_of_tenure # decays from end date, half-life ~4 years; current = 1.0
          × function_fit      # by event type or question
          × seniority_factor
rank      = relevance^0.6 × warmth^0.4
```

Output per person: one-sentence **why them**, one-sentence **what they'd know** (templated from role/function/tenure, optionally polished by BULK using pseudonymised attributes), 3 **questions to ask** (REASON or BULK, grounded in the event/research facts), relationship state ("last spoke 14 months ago"), and a **compliance flag**.

### 9.5 What the network notices (`network/insights.py`)

The brief asks for what the investor wouldn't see. Build these as small, quiet lines — not a dashboard.

- **Coverage gaps (P1, high value):** portfolio weight vs network depth per holding and per theme. "Specialty chemicals is 14% of the book. You know no one who has worked in it."
- **Keep warm (P1):** a contact's current or former employer just had a material event and you last spoke > N months ago → nudge with a 2-sentence drafted opener, copy-to-clipboard.
- **Note resurfacing (P1):** when a new filing touches a topic in the investor's own meeting notes for that company, show the note beside the filing. "Feb 2026, your note: 'management said capex would be internally funded.' Today: ₹1,200 cr QIP approved."
- **Expertise map (P1):** per theme, go-to people ranked by depth (years in theme × seniority × recency) — as a ranked list with evidence, searchable by theme.
- **Exit clusters (P2):** several people in the network left the same company's same function within a year.

### 9.6 Compliance guardrail (P0 — cheap, high signal)

If a suggested person is **currently employed** at the listed company the item is about (or is a designated/connected person there), show: "Current employee — treat as a potential insider. Don't seek unpublished price-sensitive information; keep to public and industry context." Rank former employees and adjacent-company contacts above current employees for company-specific questions. Mention in the writeup that a real deployment would log these interactions for the firm's compliance officer.

### 9.7 Person dossier (P1) (`network/dossier.py`)

For a promoter or executive: career timeline (from filings/annual report, cited), overlaps with the network (paths), prior appearances in the investor's meeting log, and "worth asking about" — gaps or short tenures in the timeline, and open items from the Promise Ledger attributed to that person's function. Facts only; no speculation about character.

---

## 10. Pull

### 10.1 Pipeline (`pull/pipeline.py`)

`run_research(symbol)` — idempotent, resumable, emits progress events:

1. Resolve the symbol (7.1). Unknown symbol → clear error with suggestions.
2. Fetch the fundamentals page; parse financial tables and document links.
3. Download the last 8 transcripts and the latest annual report (previous two if time allows); extract page text; index pages.
4. **Map (BULK, cached per document):** per transcript → claims JSON (10.3). Annual report → business/segment/MD&A extraction from routed pages only.
5. **Compute (code):** trajectory series, ratios, cash conversion, working-capital days, actuals for each claim's metric and period.
6. **Reduce (REASON, 1–2 calls):** resolve qualitative claims, write section verdict lines, bull/bear — from the compact structured inputs, not from raw documents.
7. **Verify (code):** every quote must be found in its cited page (normalised fuzzy match ≥ 0.9); every number in generated text must equal a computed value; drop or badge what fails.
8. Materialise `research_reports(company_id, version, generated_at, sections jsonb, sources jsonb, coverage jsonb)`.

Progress is streamed (SSE) and rendered as a checklist: "Found 8 transcripts · Reading Q1 FY27 call (3/8) · Checking promises against reported numbers". A cold run should finish in roughly 1–2 minutes; a cached run is instant. Pre-run and cache every portfolio and research-set company before submission.

Degradation: no transcripts → annual-report-only mode with the ledger section replaced by a plain "No earnings-call transcripts available; promises can't be tracked" notice. Missing table rows → that metric is omitted, never guessed. `coverage` records what was available so the UI can show "Based on: 8 calls, 2 annual reports, 10 years of reported financials".

### 10.2 Grounding discipline

- Every model prompt on the Pull side includes: "Use only the provided source text. If the answer is not in it, return `not_disclosed`. Do not use any other knowledge about this company."
- Inputs are source pages and computed numbers only. No web search, no news, no model recall.
- Each generated statement carries `sources: [{doc_id, page}]`. Statements without sources are dropped by the verifier.
- A small "Sources" footer on each section lists the documents used; tapping a citation opens the PDF at that page (`#page=N`).

### 10.3 The Promise Ledger — centrepiece (`pull/ledger.py`)

**Claim extraction (per transcript, BULK).** Read management's prepared remarks and answers. Extract only forward-looking statements about headline metrics:

```json
{
  "quote": "verbatim, ≤ 25 words",
  "page": 7,
  "speaker": "name", "speaker_role": "CFO",
  "made_in": "Q2 FY26",
  "metric": "revenue_growth | ebitda_margin | pat | capex | capacity | store_count |
             volume_growth | net_debt | credit_cost | nim | loan_growth | other",
  "kind": "guidance | target | commentary",
  "value_low": 20.0, "value_high": 22.0, "unit": "% | ₹ cr | count | bps",
  "target_period": "FY26 | Q3 FY26 | next 2-3 years | unspecified",
  "specificity": "numeric | directional | vague",
  "conditions": "optional caveat as stated"
}
```

**Resolution.**
- Numeric + computable metric + period elapsed → code compares against reported actuals → `delivered` / `missed` (with the gap) / `partially`.
- Period not yet elapsed → `pending`, with a run-rate line computed in code ("needs +19% in H2; H1 was +11%").
- Later calls restate the same metric with a different value → `revised` — link the chain to show **guidance drift** ("FY26 growth: 15% → 12–13% → 'low double digits'").
- Directional or vague → REASON judges against actuals and later commentary, limited to `consistent` / `contradicted` / `unverifiable`, with the evidence cited. Vague claims are listed but excluded from the score.

**Say–Do score.** `delivered ÷ (delivered + missed)` over resolved numeric claims, shown with its denominator ("Delivered 7 of 11 numeric promises, last 8 quarters"). Never show the percentage without the count. No score if fewer than 4 resolved claims.

**Presentation.** A compact table: *Said (when, who)* · *Promise* · *Due* · *Actual* · *Verdict*. Tap a row → the verbatim quote with page link, and the computed actual with its source. Above the table, one verdict line (≤ 25 words) and the drift chains.

Minimum for the brief's worked example: last four quarters, headline guidance and growth commentary, promised vs delivered. Eight quarters is better because promises need time to come due.

### 10.4 Other sections (`pull/sections.py`)

Each section = one **verdict line** (≤ 25 words, generated from computed facts) + one compact visual or table + citations + a "Who can help?" chip.

| Section | P | Content | Source |
|---|---|---|---|
| Business snapshot | P0 | What it does in 2 lines; segments with revenue mix (bar); geographies if disclosed | Annual report (routed pages) |
| Financial snapshot | P0 | TTM revenue, EBITDA margin, PAT, ROCE/ROE, net debt/EBITDA, with direction arrows | Reported financials |
| Trajectory | P0 | 5–10 year revenue / margin / PAT small multiples; CAGRs; a "growing vs compressing" split computed from trends | Reported financials |
| Promise Ledger | P0 | Section 10.3 | Transcripts + reported financials |
| Guidance | P0 | Currently open guidance only (pending claims), grouped by metric, with run-rate | Latest transcripts |
| Bull vs Bear | P0 | 3 points each, ≤ 18 words per point, each tied to a cited fact or computed number | REASON over the above |
| Balance sheet | P1 | Debt, debt-to-equity, net debt/EBITDA, interest cover, working-capital cycle in days (receivable + inventory − payable) and whether it is lengthening, funding mix trend | Reported financials + annual report |
| Cash quality | P1 | Cash from operations vs PAT by year, cumulative cash conversion, capex vs CFO, free cash flow (CFO − capex) trend; flag "profit without cash" when conversion stays below ~70% over 3+ years | Reported financials |
| Red flags | P1 | Only what is actually found, each cited to the annual-report page: **auditor's qualification** or emphasis-of-matter (from the auditor's report); **contingent liabilities** total and as % of net worth, with the largest items (from the notes); **related-party transactions** — the largest by value and any that are large relative to revenue or PAT; **promoter pledging** level and trend. If none: "Clean audit opinion; nothing unusual found" — an explicit all-clear is information too | Annual report (auditor's report, notes), shareholding, filings |

For financials (`is_financial`), swap in the appropriate metrics (NIM, loan growth, credit cost, asset quality, capital adequacy where reported) and hide what doesn't apply.

---

## 11. Frontend

### 11.1 Information architecture

Three tabs and one persistent command: **Today** · **Research** · **People** · and an **Ask** bar docked above the tab bar within thumb reach.

The Network is woven in through one repeated affordance — a **"Who can help?"** chip on every Push card and every Research section — which opens the same bottom sheet everywhere. The People tab exists for direct queries and for what the network noticed; it never opens on a list of contacts.

### 11.2 Screens

**Today (Push).**
- Header: date, window picker, the counts line ("212 filings · 4 need you · 17 worth knowing · 191 buried"), alert bell with unread count.
- *Now*: up to 5 full cards (Results / Management change / Material event / Alert).
- *Worth knowing*: single-line rows — company, class tag, the one-liner, time. Tap expands in place.
- *Buried*: one collapsed row; expands to class groups with counts ("Trading-window closures 38 · Newspaper copies 22 · …"), each filing still openable.
- End of list: "You're caught up." No infinite scroll.
- On every item: source link to the filing PDF, "Why is this here?" (score breakdown sheet), "Who can help?" when a relevant contact exists.
- P1: swipe right "this mattered" / left "noise" → adjusts `user_pref[class]`; show a tiny confirmation of what changed ("Showing fewer rating reaffirmations").

**Results card.** Company · period · consolidated/standalone · verified badge. A 4×3 grid: rows Revenue / EBITDA / PBT / PAT; columns value (₹ cr), QoQ %, YoY %. Margin line with bps change. One-line take. P1 guidance check line. Attachments from the bundle (press release, presentation, transcript).

**Management-change card.** Role and date; incoming person's fact-line bio; outgoing person and stated reason; network strip with the best path; "Open dossier".

**Material-event card.** The fact with amount and relative size ("₹1,850 cr — 22% of trailing revenue"); the so-what line; "Call {name}" with why; questions.

**Who can help? (bottom sheet).** Ranked people (max 5). Each: name (with a "synthetic" tag), current role, the why-them sentence, the path, last-contact state, compliance flag if any; expand for what-they'd-know, questions, and a drafted opener with copy button.

**Research (Pull).** Search any NSE symbol or name (typeahead over the symbol master); recent and demo companies as chips. Report = a vertical memo of section cards with a sticky section index. First card shows coverage ("Based on 8 calls, 2 annual reports…"). Uncached symbol → live progress checklist, sections appearing as they complete.

**People (Network).** A search/ask field ("Who knows about rural lending?"); below it, what FINN noticed: coverage gaps, keep-warm nudges, resurfaced notes; then themes as chips opening the expertise map. A person opens the dossier.

**Ask (P1).** One input. The agent chooses tools and returns typed blocks rendered with the same components as the rest of the app. Example prompts as chips: "What changed in my portfolio this week?", "Did {Company} deliver on its margin guidance?", "Who do I know who's worked with the new CFO at {Company}?", "Who should I call about semiconductors?".

**Settings.** Alert thresholds (sliders/steppers with live preview: "At 2.0×, this would have fired 6 times in the last 30 days"), class toggles, window default, "as of" replay, test alert, link to cost ledger, data & privacy note stating the network is synthetic.

### 11.3 Ask agent (`ask/`)

Tools: `get_brief(window)`, `get_filings(company, class, window)`, `get_research(symbol, section)`, `who_can_help(company|theme|event_id)`, `find_paths(person)`, `get_dossier(person)`, `price_stats(symbol, window)`. The model plans and calls tools; tools return data; the response is a list of **blocks** from a fixed schema — `stat_table`, `people`, `path`, `ledger_rows`, `filing_list`, `note` (≤ 2 sentences), `sources`. The model never writes free-form long text; if it tries, truncate to the `note` budget. Pull-side grounding rules apply to anything the agent says about a company's fundamentals.

### 11.4 Visual design — the no-slop rules

- **Feel:** a well-edited research note on a phone. Calm, dense, typographic.
- **Layout:** design at 390 px wide first. On desktop, centre a phone-width column; don't stretch.
- **Type:** one humanist sans for text, tabular/monospaced numerals for every number. Clear hierarchy from size and weight, not colour.
- **Colour:** near-monochrome surface; colour only carries meaning — one accent for "needs you", green/red strictly for direction, amber for caution/unverified. Support dark and light; default to system.
- **Numbers:** Indian formatting — ₹ crore (and lakh crore for very large values), one decimal; percentages one decimal; margin changes in bps; dates as "12 Nov", times in IST; periods as "Q2 FY27".
- **Density:** a *Now* card fits in one screen without scrolling. A *Worth knowing* row is one line, two at most.
- **Motion:** only functional — sheet open, expand/collapse, progress.
- **Text budgets (enforced in code):** one-liner ≤ 18 words; verdict line ≤ 25; bull/bear point ≤ 18; why-them ≤ 22; note ≤ 2 sentences.
- **Banned:** gradient blobs, sparkle icons, emoji as decoration, "AI-powered" labels, chat bubbles of prose, generic card grids, skeleton screens that outlive 4 seconds, lorem-style filler, exclamation marks, the words "insight", "delve", "leverage" in UI copy.
- **States:** every screen has designed empty, loading, stale, and error states. Empty Today: "Nothing crossed your bar in the last 24 hours. 63 routine filings buried."
- **Accessibility:** 44 px touch targets, WCAG AA contrast, colour never the only signal (use ▲▼ with green/red).
- **PWA:** manifest, icons, standalone display, theme colour; safe-area insets respected.

---

## 12. Security and privacy (design + what the prototype implements)

The writeup must cover this; `docs/ARCHITECTURE.md` gets a section with the same headings.

**What personal data exists.** (a) Contacts in the investor's network: name, employers, titles, education, years; (b) the investor's relationship metadata and meeting notes — the most sensitive data in the system; (c) public figures named in regulatory filings. The prototype holds (a) and (b) as synthetic data only, and (c) from public filings with source URLs.

**Where real profile data would come from.** Only from sources the investor is entitled to use: their own connections export from the professional network (the official "download your data" file), their own address book, calendar and CRM, their own notes, and a licensed enrichment provider under contract. No scraping of profile sites — it breaches their terms and isn't needed. Public figures: regulatory filings, annual reports, company websites.

**Keeping the network private to the investor.**
- `tenant_id` on every network table; in production, Postgres row-level security keyed to the authenticated user, with network tables in a separate schema and separate encryption key per tenant (envelope encryption; notes and relationship fields encrypted at field level).
- Market data and filings are shared, public, tenant-less. Network data never joins into shared caches: cache keys for anything derived from the network include the tenant.
- **Models see pseudonyms.** Ranking and path-finding are deterministic code. When a model polishes a "why them" line or drafts questions, it receives `P_17` with attributes (function, tenure, org), never the name or contact details; names are re-attached after the call. Implement this in the prototype — it is cheap and demonstrable.
- Personal data is sent only to no-training, zero/short-retention model endpoints in production; free tiers that may train on inputs are acceptable only because the prototype's network is synthetic.
- No personal data in logs, analytics, or the cost ledger. The public snapshot contains synthetic people only.

**Retention.** Raw imports deleted after parsing. Enriched profile fields carry `refreshed_at` and expire after 12 months unless refreshed. Removing a contact hard-deletes their rows and derived artefacts. Meeting notes live until the investor deletes them. Public-figure records are kept with provenance and corrected on request.

**Consent and access control in a real deployment.** The investor is the data fiduciary's user for their own network; the firm publishes a notice covering processing of contacts' professional data, supports access/correction/erasure requests, and records the lawful basis per source. India's DPDP Act and Rules are phasing in (substantive obligations from May 2027); don't rely on the "publicly available data" exemption, whose scope is unsettled — design for notice, purpose limitation, minimisation and erasure regardless. Access: SSO, role-based access, per-investor isolation by default with explicit opt-in sharing inside the firm, full audit log of who viewed which person, and compliance-officer visibility of insider-flagged suggestions.

**Prototype security basics (P0).** Secrets only in environment variables and GitHub/Vercel secrets; `.env.example` committed, `.env` ignored; run a secret scan before making the repo public. CORS restricted to the web origin. Write endpoints (settings, feedback, run research) rate-limited. The live research endpoint validates the symbol against the symbol master before fetching anything (no arbitrary URL fetches).

---

## 13. API surface (FastAPI)

All GET responses are render-ready view-models. Version prefix `/api`.

```
GET  /health
GET  /api/brief?window=24h|3d|7d|30d&from=&to=&as_of=
GET  /api/items/{id}                    # full card + score breakdown + sources
GET  /api/items/{id}/who                # who-can-help for an event
GET  /api/alerts?unread=
POST /api/alerts/{id}/read
GET  /api/alert-rules     PUT /api/alert-rules/{id}
GET  /api/alert-rules/preview?kind=&params=      # "would have fired N times in 30 days"
POST /api/push/subscribe  POST /api/push/test
POST /api/feedback                      # {item_id, signal: matters|noise}
GET  /api/symbols?q=
GET  /api/research/{symbol}             # cached report or 404 with {status:"not_cached"}
POST /api/research/{symbol}/run         # start job → {job_id}
GET  /api/research/jobs/{job_id}/events # SSE progress
GET  /api/network/who?company=&theme=&person=
GET  /api/network/paths?person_id=
GET  /api/network/insights
GET  /api/network/themes   GET /api/network/themes/{theme}
GET  /api/people/{id}                   # dossier
POST /api/ask                           # {query} → {blocks[]}
GET  /api/cost
```

Define Pydantic models for every response and generate the TypeScript types from the OpenAPI schema so the frontend and snapshot stay in sync.

---

## 14. Prompts (store versioned in `api/finn/llm/prompts/`)

Every prompt has: a version string (part of the cache key), a JSON schema for the output, 1–2 few-shot examples built from real filings, and an explicit "return null / not_disclosed when absent" rule. Skeletons:

**`classify_batch` (BULK).** "You are triaging Indian stock-exchange filings for a long-term equity investor. For each filing, decide its class from this list […], rate how much it could change an investor's view of the company (0–100), and write one line of at most 18 words stating the fact with its number. Most filings are routine; rate them low. Do not restate the headline. Return JSON array in input order."

**`extract_results` (BULK/VISION).** "From these pages of a quarterly results filing, copy the figures exactly as printed for the three quarter columns (current, preceding, same quarter last year). Prefer the consolidated statement. Report the unit stated in the table header. Do not compute anything. If a line is absent, return null."

**`extract_appointment` (BULK).** "From this filing, extract the change in management and the appointee's profile exactly as disclosed: education and each career position with organisation, role and years where stated. Do not add anything not in the text. Cite the page for each item."

**`extract_event` (BULK).** Fields per event type (deal: target, stake, consideration, funding, timeline; capex: amount, capacity, location, funding, commissioning; litigation: forum, counterparty, amount, stage).

**`extract_claims` (BULK).** "From this earnings-call transcript, extract every forward-looking statement by management about revenue, growth, margins, profit, capex, capacity, debt or sector-specific headline metrics. Quote verbatim (≤ 25 words) with page number and speaker. Ignore analyst speech and historical description. Classify specificity honestly: 'we remain confident' is vague." Schema as in 10.3.

**`resolve_ledger` (REASON).** Input: claims JSON, computed actuals per metric and period, later-quarter claims on the same metric. "For each non-numeric claim decide consistent / contradicted / unverifiable using only these inputs, and cite the evidence. Then write one verdict line (≤ 25 words) on how reliably management's guidance has translated into results. Do not use outside knowledge."

**`bull_bear` (REASON).** Input: computed facts and section outputs only. "Three points each way, ≤ 18 words each, each tied to one cited fact. No generic statements that could apply to any company."

**`why_them` / `questions` (BULK).** Pseudonymised person attributes + event facts → one sentence (≤ 22 words) and three specific questions. "Questions must be answerable from the person's actual experience and must not ask for confidential or unpublished information."

---

## 15. Quality: tests, evals, verification

- **Unit tests (P0)** for everything deterministic: results arithmetic and unit normalisation, EBITDA formula, QoQ/YoY, scoring, tier caps, bundling, alert thresholds and idempotency, link strength, path scoring, name/organisation normalisation, the citation verifier, Indian number and fiscal-period formatting.
- **Golden files (P0):** 5 real results PDFs (one bank, one scanned, one with exceptional items, one standalone-only, one in lakhs) with hand-checked expected values; 3 real appointment filings; 2 transcripts with hand-listed claims.
- **Classifier eval (P1):** `data/eval/labelled.jsonl` — ~120 real filings hand-labelled with class and tier. `finn eval classify` reports accuracy by class, the precision/recall of the *Now* tier, share decided by rules, and cost per 1,000 filings. Put the table in `docs/evals.md` and one line in the writeup. Few candidates will have measured their filter; this is the cheapest way to show depth.
- **Generalisation check (P0):** run the research pipeline on 5 symbols outside all demo sets (include one small cap and one financial). Record results and failures honestly in `docs/evals.md`.
- **CI:** lint, type-check, unit tests on every push.
- **Phone check (P0):** every P0 flow exercised on a real iPhone (Safari) and Android (Chrome) against the deployed URL.

---

## 16. Build plan

This is an order of work with gates, not a schedule. Deploy in Phase 0 and keep it deployed throughout.

**Phase 0 — skeleton and deploy.**
Repo, FastAPI hello, Next.js shell with three tabs, Postgres connected, both deployed, CI green, snapshot fallback wired with dummy JSON.
*Gate 0a (local):* the app opens on a phone over Wi-Fi and shows data from the API, and from the snapshot when the API is stopped.
*Gate 0b (deployed):* the same on the deployed URLs. *[Changed 2026-11-12: split because accounts are created after 0a.]*

**Phase 1 — data plumbing.**
Symbols, prices, NSE filings with PDF text, NSE structured results + annual-report and transcript links, LLM router + cache + ledger. `pick_portfolio.py` run and portfolio fixed. 120-day backfill.
*Gate:* `finn ingest all` fills the DB for 18 companies without manual steps; row counts printed.

**Phase 2 — Push core.**
Rules classifier → batch LLM classifier → bundling → scoring → tiers → digest API → Today screen with *Worth knowing* and *Buried*. Results card end-to-end with validation.
*Gate:* the 7-day brief on the phone shows correct tiers and at least 5 verified results cards whose numbers match the PDFs by hand.

**Phase 3 — Network + rich cards.**
Generate network, entity resolution, strength, who-can-help, paths. Management-change and material-event cards with the Who-can-help sheet. Compliance flag. Alerts with settings and in-app inbox.
*Gate:* a real management-change filing shows the incoming person's bio from the filing and a second-degree path; a material event shows "Call {name}" with a defensible reason; changing a threshold changes which alerts fire.

**Phase 4 — Pull.**
Research pipeline, P0 sections, Promise Ledger with verifier, live progress, pre-cache all demo companies, generalisation check.
*Gate:* the hero company's ledger has ≥ 5 resolved numeric claims, each fully cited (quote with
page and transcript link; actual with its filing), none padded; an unseen ticker completes live on
the phone. *[Changed 2026-11-13 by the owner from ≥ 8: hero is KAYNES.]*

**Phase 5 — the differentiators (all of P1).**
In this order: results↔ledger link; Balance sheet, Cash quality and Red flags sections; coverage gaps, keep-warm and note resurfacing; person dossier; Ask bar; unexplained-move alerts; Web Push; swipe feedback; classifier eval harness.
*Gate:* each P1 item works on the phone against real data, or is removed entirely — no half-built features left visible.

**Phase 6 — polish and proof.**
Design pass against 11.4 on every screen, empty/error/stale states, cost ledger screen, README, ARCHITECTURE, diagram, WRITEUP. Export snapshot. Secret scan. Make repo public. Fresh-device test on iPhone and Android; record a 2–3 minute screen capture as insurance.
*Gate:* section 18 checklist fully ticked.

Standing rule: never trade a P0 gate for a P1 feature, and never leave something broken on screen. If a feature can't be made correct, hide it and list it under "left out" in the writeup.

---

## 17. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| Exchange / Yahoo block cloud IPs (NSE refuses Render, verified) | Ingest runs in the scheduled job or locally and writes to the DB; serving never depends on them. For live research from the server, cache documents aggressively and show a clear "source unreachable — try again" state rather than failing silently. |
| Free-tier quota exhausted mid-build | Multi-provider router; cache everything; pre-compute demo companies early (start Phase 4 caching the evening before). No paid fallback (zero spend). *[Changed 2026-11-12.]* |
| Scanned results PDFs | VISION fallback; if it fails validation, show the card as "unverified" with the filing link rather than wrong numbers. |
| Backend asleep when the grader opens the link | Keep-alive pings, Vercel cache, snapshot fallback, warm-up on load. |
| Database paused for inactivity | Keep-alive query on a schedule; snapshot fallback. |
| Model returns invalid JSON or invents content | Schema validation + one repair retry; citation verifier; numbers only from code. |
| No interesting filings on the day it's opened | Longer default windows available; "as of" replay; portfolio chosen for real recent events. |
| Wrong numbers on a results card | Validation + cross-check + golden-file tests; unverified badge. A wrong number in front of an investment firm is worse than a missing one. |
| Scope creep | The standing rule in section 16: correct or hidden, never half-built. |

---

## 18. Submission checklist

**Prototype**
- [ ] Public URL opens on iPhone Safari and Android Chrome with no login and no install.
- [ ] Push: digest with window picker; three rich card types on real filings; buried pile; alerts with editable thresholds.
- [ ] Pull: hero company report with Promise Ledger and working citations; an arbitrary NSE ticker runs live.
- [ ] Network: Who-can-help on cards and research sections; second-degree path; direct query.
- [ ] Synthetic data labelled as synthetic in the UI.
- [ ] Snapshot fallback verified by stopping the API.
- [ ] Cost ledger screen shows real figures.

**Repository (public)**
- [ ] README: what it is, the point of view in 5 lines, screenshots, live link, a 2-minute "try this" path, local setup, env vars, how to run ingest, what's real vs synthetic, limitations.
- [ ] `docs/ARCHITECTURE.md` with diagram; `docs/DECISIONS.md`; `docs/evals.md`.
- [ ] No secrets in history. Licence file. CI passing.

**AI build history**
- [ ] Every coding-agent and chat session exported or share-linked into `docs/build-log/` with an index: date, tool, goal, outcome, and where the model was wrong and what was done about it.
- [ ] This spec included as `docs/SPEC.md`, with a note on which parts were changed during the build and why.

**Email** — to `assessment@enam.com`, subject `IIT Kanpur – Founding AI Engineer - 2027`
- [ ] Live link, repo link, build-history links, optional short screen recording.
- [ ] Writeup in the body (section 19).
- [ ] States clearly: network profiles are synthetic; how it would be done for real.

---

## 19. Writeup skeleton (covering email, ~500–700 words)

1. **What I built** — two sentences and the live link. The point of view: a finite briefing that answers *what changed, so what, who can help*.
2. **Three things to try on your phone** — a results card; a management-change card with its network path; the Promise Ledger on Kaynes; then "type any NSE ticker".
3. **Key decisions and trade-offs** — rules-before-models filtering with a visible buried pile; bundling; computed numbers with validation; closed-book research with a citation verifier; deterministic, explainable network scoring; materialised views so the read path makes no model calls.
4. **Architecture**
   - *Data pipelines:* sources, cadence, storage, entity resolution (how a name in a filing becomes a person in the network, with confidence).
   - *Security & privacy:* synthetic network and why; tenant isolation; pseudonymised model calls; retention; consent and access control in production; the insider flag.
   - *LLMs & agents:* the tier table — which step uses which model and why; where the agent plans and calls tools (Ask, research pipeline); measured cost and cache-hit rate; classifier eval numbers.
   - *Cloud:* what runs where and why; resilience layers.
5. **What I deliberately left out** — and why each was the right cut.
6. **Where I'd take it next** — exchange feed for true real-time; the investor's real connections export, calendar and CRM; supplier/customer graph from annual reports; firm-wide (opt-in) network; feedback-trained ranking; voice brief; compliance logging.
7. **How I worked with AI tools** — two or three honest examples of a wrong turn and the correction, linking to the build log.

Keep it plain. No adjectives about the product; let the three things to try do the selling.

---

## 20. Standing rules for agents (repeat of the essentials)

1. Real market data only; synthetic people only; label both.
2. Models extract and explain; code computes and ranks.
3. No claim without a source; no number without validation.
4. Cache by content hash; never read a document twice.
5. Rules → cheap model → strong model, in that order, and log every call.
6. The read path makes no model calls.
7. Every generated string has a word budget enforced in code.
8. Deployed and working on a phone at the end of every phase.
9. Log decisions as you make them.
10. When in doubt between adding a feature and making an existing one correct, make it correct.