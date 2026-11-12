# Phase gates — evidence log

One entry per phase gate (spec §16), with the real output that showed it passing. Newest last.

## Phase 0a — local skeleton ✅ 2026-11-12
- Gate: app opens on a phone over Wi-Fi with data from the API, and from the snapshot when the
  API is stopped.
- Evidence: CDP-emulated 390×844 iPhone at `http://172.23.70.20:3000` — API up: badge
  "Live · as of 12 Nov, 14:37 IST", `scrollWidth` 390; API process killed: badge "Snapshot · as
  of 12 Nov, 14:37 IST". Owner then confirmed on their own phone ("yup it works").
- Checks: API 5 tests, web 5 tests, ruff/mypy/eslint/tsc clean, `next build` ok; API Docker image
  runs against local Postgres.

## Phase 0b — deployed ✅ 2026-11-12
- Gate: same on the public URLs.
- Evidence: `https://finn-api-mxni.onrender.com/health` → `{"status":"ok","env":"render","db":"ok"}`
  (Neon); CORS header `access-control-allow-origin: https://finn-tawny-nine.vercel.app`; emulated
  phone on `https://finn-tawny-nine.vercel.app` → "Live · as of 12 Nov, 16:38 IST"; with
  `*onrender.com*` blocked → "Snapshot · as of 12 Nov, 14:37 IST"; no horizontal scroll.

## Phase 1 — data plumbing ✅ 2026-11-12
- Gate: `finn ingest all` fills the DB for the demo companies without manual steps; row counts
  printed.
- Evidence (`finn ingest all` into Neon, second run after the 404 fix; 478 NSE requests, 79 cache
  hits, one at a time ≥ 1.2 s apart, no refusals):
  ```
  symbols       {'symbols': 2635}
  prices        {'price_rows': 5703, 'tickers': 23, 'tickers_missing': 0}
  filings       {'filings_upserted': 1199, 'transcript_links': 39}
  transcripts   {'transcript_links': 196}
  fundamentals  {'annual_report_links': 321, 'xbrl_already': 226, 'xbrl_parsed': 314, 'xbrl_missing': 3}
  texts         {'texts_fetched': 130}
  companies 2,636 · prices 5,703 · filings 1,199 · documents 513 · fin_filings 540 · fin_facts 72,803
  ```
  22 demo companies (18 portfolio + 4 research), each with 248 price days, 27–98 filings,
  8–12 transcript links (TRENT 0), 4–18 annual-report links, 15–26 XBRL results filings.
- Measured depth (stored as `coverage:<SYMBOL>` views): XBRL from 2017–2020 (KAYNES Dec 2022, its
  listing); ~8 fiscal years of P&L, ~4.5 years of balance sheets (9 half-year points), 3–4 years
  of annual cash flow. AUBANK has standalone only.
- LLM router: live call through local Ollama (qwen2.5:7b) → validated JSON, cached; second call a
  cache hit (52.5 s → 0.6 s); both in the `llm_calls` ledger at ₹0.
- Tests: 17 offline Phase 1 tests + Phase 0 tests; ruff and mypy clean.

## Phase 2 — Push core ✅ 2026-11-13
- Gate: the 7-day brief on a phone shows correct tiers and ≥ 5 verified results cards whose
  numbers match the filing PDFs.
- **Window used:** 7 days replayed as of 31 Oct 2026, 21:00 IST (spec §8.8 "as of" control) —
  most portfolio results were filed in late October, so the last 7 days held only one. Deep
  link: `https://finn-tawny-nine.vercel.app/?w=7d&as_of=2026-10-31`.
- Evidence (CDP-emulated 390×844 iPhone, public URLs, `scrollWidth` 390):
  - Replay: "75 filings · 5 need you · 11 worth knowing · 39 buried", "Live · as of 31 Oct,
    21:00 IST"; Now = results cards for DEEPAKNTR (85), SUNPHARMA (83), LT (75), VBL (74),
    DIXON (74); HDFC Bank's MD & CEO change in Worth knowing. Replay served by Render in 0.6 s.
  - API blocked (`*onrender.com*`): normal 7d view renders the exported snapshot ("Snapshot · as
    of 12 Nov, 20:03 IST"); a replay shows "Replays are built live and the API isn't reachable".
- **Numbers vs PDFs** (every printed figure found in the results PDF text, after OCR-digit repair,
  under the filing's own unit, within rounding): DIXON (₹ cr), SUNPHARMA (₹ mn), LT (₹ cr), VBL
  (₹ mn), KPITTECH (₹ mn) — 5 cards fully matched. HDFCBANK PAT matched by eye (`2O7OO.O3` =
  ₹20,700.03 cr, OCR letter O). DEEPAKNTR's PDF is a scan (no text layer) and MARUTI's text layer
  is garbled OCR: not text-verifiable; both still pass the filing's own XBRL identities.
- Classifier: 1,199 filings — 947 by rules, 250 by qwen2.5:7b (53 calls, 65k in / 17.5k out
  tokens, ₹0), 2 retried and placed. Eval in `docs/evals.md` (86.8% end to end).
- Tests: API 32 (incl. 9 Phase 2), web 6; ruff, mypy, eslint, tsc clean; `next build` ok.

## Phase 3 — Network + alerts ✅ 2026-11-13
- Gate: a real management-change filing shows the bio and a second-degree path; a material event
  shows "Call {name}"; changing a threshold changes which alerts fire.
- Evidence (local web on the exported snapshot, 500 px headless Chrome):
  - HDFCBANK MD & CEO filing (ids 383/368): card strip reads "You were at ICICI Bank 2014–2017
    while Anup Bagchi was there"; the sheet shows his career as disclosed in the filing (ICICI Bank
    1992–, ED 2017–2023, ICICI Prudential Life MD & CEO 2023–) and three paths, top: "You → Nikhil
    Gill (personal, 9 interactions in 24 months) → Anup Bagchi: overlapped at ICICI Bank" (strong
    × medium). Network adds +10 to the score; it is in Now in the 3 Oct replay.
  - Material events: TATASTEEL M&A → "Call Kabir Agarwal"; DIXON management change → "you can
    reach Prithvi Vachani through Shreya Gill"; current employees carry the insider flag.
  - Alerts over 30 days: 2×/±4% → 101 (40 volume, 18 price, 43 filings); 3×/±6% → 65 (17, 5, 43);
    1.5×/±2% → 241. Python and TypeScript evaluators agree on a shared fixture (tests both sides).
- Data: 64 synthetic contacts + 8 planted overlaps with executives named in filings, 40 meetings,
  17 public figures from 13 filings. Tests: API 46, web 9; ruff, mypy, eslint, tsc clean.

## Phase 4 — Pull (partial, 2026-11-13)
- Built: `finn research SYM` for any NSE ticker with XBRL results + call transcripts — 12 quarters
  of numbers from XBRL; guidance from the last 4 earnings calls (rules, then qwen2.5 7B; every quote
  verified verbatim in the transcript, page kept); band changes computed (raised/held/cut);
  verdicts against filings; computed bull/bear; who-to-call from the network.
- INFY (hero): FY27 revenue-growth guidance 1.5–3.5% → 1.5–3% → 1–2% (cut twice); FY27 operating
  margin 20–22% held, filings 21.0% (2Q YTD) → on track; FY26 margin delivered (20.9%). Revenue
  guidance is constant-currency, so it is marked "not comparable" with reported ₹ growth rather
  than scored. CREDITACC: ROA 4–4.8% → 5.2–5.8% and ROE 16–20% → 21–24% raised. TRENT: no
  transcripts → honest empty state.
- Gate not fully met: INFY has 8 cited guidance points but only 2 resolved verdicts (≥ 8 asked);
  an unseen ticker cannot run live on the phone because Render can't reach NSE — it runs on the
  worker (`finn research SYM`) and the page says so.
