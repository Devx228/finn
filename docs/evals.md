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
