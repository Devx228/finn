"""Guidance-extraction eval against hand-listed claims (data/eval/guidance_gold.json).

For each model: the model alone on the selected sentences (raw, and after the strict confidence
check), and the shipped pipeline (rules + model + strict). Precision = kept items matching a gold
claim / kept items; recall = gold claims found / gold claims. Each model gets its own tier name so
cache entries are never shared between models.
"""

from __future__ import annotations

import json
import os

from finn import db
from finn.config import REPO_ROOT
from finn.llm.router import Router
from finn.llm.store import LLMStore
from finn.pull import guidance as gd

GOLD = REPO_ROOT / "data" / "eval" / "guidance_gold.json"


def _match(item: dict, claim: dict) -> bool:
    if item["metric"] not in claim["metrics"] or item.get("period") not in claim.get(
        "periods", [claim["period"]]
    ):
        return False
    lo, hi = item.get("low"), item.get("high")
    return any(
        lo is not None and abs(lo - a) < 1e-6 and abs((hi or lo) - b) < 1e-6 for a, b in claim["bands"]
    )


def score(items: list[dict], claims: list[dict]) -> dict:
    tp = sum(any(_match(i, c) for c in claims) for i in items)
    found = {c["id"] for c in claims if any(_match(i, c) for i in items)}
    wrong = [
        f"{i['metric']} {i.get('period')} {i.get('low')}-{i.get('high')}: {i['quote'][:70]}"
        for i in items
        if not any(_match(i, c) for c in claims)
    ]
    return {"kept": len(items), "correct": tp, "found": sorted(found), "wrong": wrong}


def _n(t: str) -> str:
    return " ".join(gd._norm(t).split())


def negatives(items: list[dict], negs: list[dict]) -> list[dict]:
    """A negative is violated when an item drawn from that sentence would be scored: it names a
    fiscal year and isn't marked as one business's figure."""
    out = []
    for ng in negs:
        key = _n(ng["quote"])[:60]
        hits = [
            i
            for i in items
            if (key in _n(i["quote"]) or _n(i["quote"])[:60] in _n(ng["quote"]))
            and str(i.get("period", "")).startswith("FY")
            and i.get("scope") != "segment"
        ]
        out.append(
            {
                **ng,
                "violated": bool(hits),
                "by": [f"{i['metric']} {i['period']} {i['low']}-{i['high']}" for i in hits],
            }
        )
    return out


def run(models: list[str]) -> dict:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    out: dict = {}
    with db.connection() as conn:
        docs = {
            d["doc_id"]: conn.execute("SELECT pages FROM documents WHERE id = %s", (d["doc_id"],)).fetchone()[
                0
            ]  # type: ignore[index]
            for d in gold["docs"]
        }
    configs: list[tuple[str, str | None, bool, bool]] = [("rules only", None, True, True)]
    for m in models:
        configs += [
            (f"{m} · model alone, raw", m, False, False),
            (f"{m} · model alone, strict", m, True, False),
            (f"{m} · rules + model + strict", m, True, True),
        ]
    for i, (name, route, strict, rules) in enumerate(configs):
        router = None
        tier = "BULK"
        if route:
            tier = f"EVALG{models.index(route)}"
            os.environ[f"LLM_TIER_{tier}"] = route
            router = Router(store=LLMStore())
        tot: dict = {
            "kept": 0,
            "correct": 0,
            "gold": 0,
            "found": [],
            "wrong": [],
            "drop_reasons": {},
            "negatives": [],
        }
        for d in gold["docs"]:
            items, st = gd.extract(
                router, docs[d["doc_id"]], d["call_fy"], tier=tier, strict=strict, use_rules=rules
            )
            s = score(items, d["claims"])
            tot["negatives"] += [
                {**x, "symbol": d["symbol"]} for x in negatives(items, d.get("negatives", []))
            ]
            tot["kept"] += s["kept"]
            tot["correct"] += s["correct"]
            tot["gold"] += len(d["claims"])
            tot["found"] += s["found"]
            tot["wrong"] += [f"{d['symbol']}: {w}" for w in s["wrong"]]
            for k, v in st.get("drop_reasons", {}).items():
                tot["drop_reasons"][k] = tot["drop_reasons"].get(k, 0) + v
            if str(st.get("model_name") or "").startswith("unavailable"):
                tot["error"] = st["model_name"]
        tot["precision"] = round(tot["correct"] / tot["kept"], 2) if tot["kept"] else None
        tot["recall"] = round(len(tot["found"]) / tot["gold"], 2)
        ok = [x for x in tot["negatives"] if not x["violated"]]
        tot["negatives_held"] = f"{len(ok)}/{len(tot['negatives'])}"
        kinds: dict[str, list[int]] = {}
        for x in tot["negatives"]:
            k = kinds.setdefault(x["kind"], [0, 0])
            k[0] += not x["violated"]
            k[1] += 1
        tot["negatives_by_kind"] = {k: f"{a}/{b}" for k, (a, b) in kinds.items()}
        out[name] = tot
        print(
            f"{name:55s} P={tot['precision']} R={tot['recall']} kept={tot['kept']} "
            f"negatives held={tot['negatives_held']} "
            f"{'ERR ' + tot['error'] if 'error' in tot else ''}",
            flush=True,
        )
        _ = i
    return out
