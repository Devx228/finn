"""Classifier evaluation against data/eval/labelled.jsonl (spec §15).

Rules are scored on every labelled filing they decide. Each candidate model is scored on the
filings the rules leave undecided (the only ones a model ever sees in production). Each model
gets its own tier name (EVAL_<n>) so cache entries are never shared between models.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter

from finn import db
from finn.config import REPO_ROOT
from finn.llm.router import Router
from finn.llm.store import LLMStore
from finn.push import classify_llm as cl
from finn.push.classify_rules import classify

LABELS = REPO_ROOT / "data" / "eval" / "labelled.jsonl"


def load() -> list[dict]:
    rows = [json.loads(x) for x in LABELS.read_text(encoding="utf-8").splitlines() if x.strip()]
    with db.connection() as conn:
        for r in rows:
            cat, subj, pages = conn.execute(  # type: ignore[misc]
                "SELECT exch_category, subject, text_pages FROM filings WHERE id = %s", (r["filing_id"],)
            ).fetchone()
            r.update(exch_category=cat, subject_full=subj, pages=pages)
    return rows


def eval_rules(rows: list[dict]) -> dict:
    decided = right = 0
    misses = []
    for r in rows:
        c = classify(r["exch_category"], r["subject_full"], " ".join(r["pages"][:2]) if r["pages"] else None)
        if c is None:
            continue
        decided += 1
        if c.category == r["category"]:
            right += 1
        else:
            misses.append((r["filing_id"], r["category"], c.category, r["subject"][:90]))
    return {
        "labelled": len(rows),
        "rules_decided": decided,
        "rules_correct": right,
        "rules_accuracy": round(right / decided, 3) if decided else None,
        "misses": misses,
    }


def eval_model(rows: list[dict], route: str, n: int) -> dict:
    todo = [
        r
        for r in rows
        if classify(r["exch_category"], r["subject_full"], " ".join(r["pages"][:2]) if r["pages"] else None)
        is None
    ]
    tier = f"EVAL_{n}"
    os.environ[f"LLM_TIER_{tier}"] = route
    router = Router(store=LLMStore())
    right, invalid, secs = 0, 0, 0.0
    by_cat: Counter = Counter()
    misses: list[tuple] = []
    for i in range(0, len(todo), cl.BATCH):
        batch = todo[i : i + cl.BATCH]
        payload = [
            {
                "exch_category": r["exch_category"],
                "subject": r["subject_full"],
                "text": (
                    " ".join(r["pages"][:2]) if r["pages"] and cl.thin_subject(r["subject_full"]) else None
                ),
            }
            for r in batch
        ]
        t0 = time.monotonic()
        try:
            res = router.call(
                tier,
                "eval_classify",
                cl.PROMPT_VERSION,
                cl.SYSTEM,
                cl.render_batch(payload),
                cl.Batch,
                cache_payload=payload,
            )
            got = {it.idx: it.category for it in res.data.items}  # type: ignore[attr-defined]
        except Exception as e:  # count the whole batch as wrong, keep going
            got, invalid = {}, invalid + len(batch)
            misses.append(("batch", str(e)[:120]))
        secs += time.monotonic() - t0
        for j, r in enumerate(batch):
            ok = got.get(j) == r["category"]
            right += ok
            by_cat[(r["category"], ok)] += 1
            if not ok:
                misses.append((r["filing_id"], r["category"], got.get(j), r["subject"][:80]))
    return {
        "route": route,
        "n": len(todo),
        "correct": right,
        "accuracy": round(right / len(todo), 3) if todo else None,
        "invalid_outputs": invalid,
        "seconds": round(secs, 1),
        "sec_per_filing": round(secs / len(todo), 2) if todo else None,
        "misses": misses,
    }
