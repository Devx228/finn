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
