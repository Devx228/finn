# Evaluations

## Filing classifier (spec §15) — 2026-11-12/13

**Labelled set:** `data/eval/labelled.jsonl` — 114 real NSE filings from the 22 demo companies,
drawn deterministically (ordered by `md5(exch_id)`): 60 the first rules version could not place
and 60 it did, spread across categories. Labelled with the 17 reference categories and an
expected tier. **Labeller: the coding agent (Claude), from each filing's subject and PDF text**,
not a human analyst; 6 more were excluded because no text was available to label from
(`data/eval/excluded.json`). Treat this as a working benchmark, not ground truth.

**Caveat — the same set was used to improve the system.** Prompt v2 and rules v2/v3 were written
after reading v1's misses, so later numbers on this set are optimistic. A fresh held-out set is
the right next step.

### Rules (stage 1, zero cost)

| Version | Decided (of 114) | Correct | Accuracy | Share of all 1,199 filings decided |
|---|---|---|---|---|
| v1 | 60 | 59 | 98.3% | 74% |
| v2 (+ promoter-encumbrance rule) | 60 | 60 | 100% | 74% |
| v3 (+ ESG, conferences, recordings, volumes, results releases, address changes, top-role change stated in the letter) | 76 | 76 | 100% | 79% |

### Local models on the filings the rules leave (stage 2)

All on the owner's RTX 4050 (6 GB) via Ollama 0.5.13, temperature 0, strict JSON schema.

| Model | Prompt | n | Accuracy | Invalid outputs | s / filing |
|---|---|---|---|---|---|
| qwen2.5:7b | v1 (batch 10, first 1,500 chars of the PDF) | 54 | 37.0% | 0 | 5.2 |
| llama3.1:8b | v1 | 54 | 27.8% | 10 (one batch timed out) | 7.1 |
| qwen2.5:3b | v1 | 54 | 33.3% | 0 | 1.4 |
| qwen2.5:7b | v2 (batch 5, text from the letter's "Sub:" line, two few-shot examples) | 54 | 59.3% | 0 | (cached)* |
| qwen2.5:3b | v2 | 54 | 44.4% | 0 | 1.6 |
| qwen2.5:7b | v2, after rules v3 (harder remainder) | 40 | 62.5% | 0 | 7.0 |

\* v2 7b answers were computed by an earlier run that was stopped for memory; the re-run read
them from the cache, so its time is not meaningful.

**v1 failure analysis:** batches of 10 made small models drop or renumber items (runs of empty
answers); the first 1,500 characters of a PDF are letterhead and exchange addresses, not content;
no examples. Fixing input and batch size moved qwen2.5:7b from 37% to 59%.

**Choice: qwen2.5:7b** as the local BULK model (best accuracy, no invalid output). llama3.1:8b
dropped (least accurate, slowest, invalid outputs); qwen2.5:3b is 4× faster but 15 points worse.

### End to end (rules v3 → qwen2.5:7b)

**99 of 114 correct (86.8%).** Every rules decision was right; all 15 errors are model errors on
filings whose subject says nothing ("General Updates"). Remaining error pattern: the model calls
client wins and announcements "unclassified" and confuses M&A with fund raising.

**Implication for the product:** the model's mistakes land mostly on low-materiality filings, but
not all — before rules v3 it labelled HDFC Bank's MD & CEO disclosure "M&A". So material
categories are caught by rules wherever a deterministic signal exists, and model-decided items
are badged as such in "Why is this here?". To try next, in order: a hosted model on the hard
remainder only (~20% of filings) once a Gemini key exists; a held-out labelled set; per-class
precision/recall of the *Now* tier.

### Misalignment guard (2026-11-13)

Batches of five sometimes produced an answer for the wrong filing. Prompt v3 adds a per-filing
`ref` the model must echo (mismatches rejected and retried), company-grouped batches, and a
post-check that drops a one-liner naming a company absent from the filing. Re-run of all 252
model-decided filings: 24 answers rejected and retried; one-liners naming another demo company
went from 5 to 1 (dropped by the post-check); 3 filings left unclassified rather than mislabelled.
Category accuracy on the labelled set was not re-measured for v3.

## Guidance extraction: hosted vs local (2026-11-13)

**Gold set** (`data/eval/guidance_gold.json`), hand-listed by reading every forward-looking
numeric sentence of two transcripts: Infosys Q4 FY26 call (large company, 46 pages: FY27 revenue
growth 1.5–3.5% cc, FY27 operating margin 20–22%) and Kaynes Q1 FY27 call (small company, 20
pages: FY27 capex ₹300 + 300 + 250 cr, FY27 OSAT+PCB revenue ₹450–500 cr — a segment target).
4 claims and 14 listed distractors (analysts restating guidance, past actuals, tax rate, hiring,
margin bridges, broker estimates, order book, prices). Small by design — two transcripts as asked
— so a single miss moves recall by 25 points; read the per-claim results, not just the ratios.
Runner: `finn.pull.eval_guidance.run([...])`.

| System | Precision | Recall | Notes |
|---|---|---|---|
| Rules only (no model) | 1.00 (3/3) | 0.75 | misses the segment revenue target |
| qwen2.5 7B (local) alone | 1.00 (2/2) | 0.50 | one quote not verbatim (dropped) |
| gemini-3.5-flash-lite alone | 1.00 (3/3) | 0.75 | misses capex |
| **gemini-3-flash-preview alone** | **1.00 (4/4)** | **1.00** | |
| gpt-oss-120b (Groq) alone, raw | 0.83 (5/6) | 1.00 | called "INR180 crores, sorry" (Q1 spend) a capex target |
| gpt-oss-120b alone + strict check | 1.00 (5/5) | 1.00 | the confidence check dropped it: metric not named in the quote |
| Pipeline (rules first, model adds non-conflicting items, strict) with gemini-3-flash / 3.5-flash-lite / gpt-oss | 1.00 | 1.00 | |
| Pipeline with local qwen | 1.00 | 0.75 | |

Two bugs the eval found, both fixed before these numbers: (1) sentences were split per page, so a
sentence running over a page break lost its subject ("…revenue of totally INR500 crores between
both, | INR450 to INR500 crores, which is what we are targeting") — sentences now span pages and
running headers are stripped; (2) rules read that ₹ figure as *company* revenue (which would have
been "delivered" against ₹4,000 cr of revenue) — a ₹ revenue/capex figure in a sentence naming a
business/segment is now `segment` scope and never scored against company totals.

**Merge order, decided on production output, not the gold set:** a model-first merge (model's
reading of a sentence replaces the rule's) scored the same on the gold set but, on CREDITACC, the
model labelled "ROA of 5.2% to 5.8%" as profit growth and the rule-read ROA/ROE items for that
sentence were lost. Rules are positional (each metric keyword takes its own number), so they now
go first; a model item is added only if it doesn't conflict with a rule item in the same sentence
(same metric or same number). Re-run on the final code: numbers above unchanged.

**Further precision guards from reading every resolved track (6 companies):** analyst paraphrases
("which you have told us"), TCV/bookings ("on TCV it was just 4%") → skipped; aspirations and
multi-year totals ("over a period of time", "across these four years", "total spend") → period
`medium term`, listed but never scored; a year with no results yet → `pending`; cost-to-income
not scored (CREDITACC reports 34.1%; opex ÷ (income − finance cost) from XBRL gives ~29% — the
company's definition can't be rebuilt, so a "beat" would be ours, not theirs).

**Choice:** tier `EXTRACT` = gemini-3-flash-preview → gemini-3.5-flash-lite → gpt-oss-120b →
local qwen2.5. Best by the numbers; Flash-Lite as first fallback (15 req/min vs 5); gpt-oss only
behind the strict check; local model when no key. Every model item must also pass the strict
check (management + forward-looking + high confidence + metric named in its own quote + the band's
numbers present in the quote), and every quote must be verbatim in the transcript.

## Guidance negatives (live-run regression set), 2026-11-13
`data/eval/guidance_negatives.json`: five POLYCAB sentences that earlier rules turned into scored
claims (an achievement, a reported calendar-year figure, an export-mix target, a restated segment
actual, a yearless long-term band). Each must yield no claim, or only an open one; checked in
`api/tests/test_pull.py::test_polycab_negatives_never_become_scored_claims` (passes). Ledger
re-run under the stricter rules: resolved KAYNES 5→3, POLYCAB 4→0, CREDITACC 5→5, INFY 2→2, LT 1→1.

## Ranking regression set and classifier, before/after the ranking fix (2026-11-13)
| | Before | After |
|---|---|---|
| Labelled filings | 114 | 124 (+10 ranking regressions; 4 existing rows given expected ranges) |
| Rules: decided / correct category | 76 / 76 (1.000) | 85 / 85 (1.000) |
| Severity regressions (base within the expected range) | not measured (4 of the 14 would have passed: the Airtel penalties at 34 were above 20) | 13 / 14 |
The one miss: Sun Pharma ILUMYA US approval, hosted-model base 39 vs expected ≥ 40 (it still
shows in Worth knowing). `python -m finn.push.evaluate` reports both; expected ranges are set from
judgment about the filing, not from the scorer's output.

## Guidance extraction, 26 hand-listed claims + 25 negatives (2026-11-13)
Gold (`data/eval/guidance_gold.json`, for the owner to check): 8 transcripts — CreditAccess ×3
(May 2025, May 2026, Oct 2026), Kaynes ×3, Infosys ×1, Polycab ×1 — 26 numeric guidance claims by
management, each with its quote and page, and 25 **negatives**: sentences that must never become a
scored claim, of the kinds that fooled earlier versions (achievements/results 8, share-of-revenue
targets 5, segment figures 4, long-term bands with no year 3, multi-year totals 3, restated old
goals 2). Three CreditAccess claims say "retain/maintain/expect" without naming the year; the gold
accepts FY27 or "no year stated" for them (the extractor never assigns a year the quote doesn't name).

| Config | Precision, all kept | Precision, items held to a year | Recall | Negatives held |
|---|---|---|---|---|
| Rules only | 0.85 (22/26) | 22/22 | 0.85 | 25/25 |
| Hosted model alone, raw | 0.55 | — | 0.42 | 24/25 (scored "₹4,800 cr capex to FY28-29" as FY28) |
| Hosted model alone, strict | 0.69 | — | 0.35 | 25/25 |
| **Shipped: rules + model + strict** | **0.79 (23/29)** | **23/23** | **0.88** | **25/25** |

All 6 "wrong" items in the shipped config are open items (no year / medium term: Kaynes "40–50%
on its own", Polycab "15–20%" derived growth, Polycab/Kaynes multi-year capex): listed, never
scored. Missed (3): CreditAccess "We expect a NIM of 14.4% to 14.7% as against 12.8% to 13.2%"
(the "as against" skip), Kaynes "cross the operational EBITDA of 15% this year" (no "margin"
word), Polycab FY25 capex "₹10 billion to ₹12 billion … during this year" (the sentence opens with
the Q3 actual). Engine frozen (owner, 2026-11-13): these stay documented, not fixed.
The earlier "precision 1.0 on 4 claims" is superseded by this set.
