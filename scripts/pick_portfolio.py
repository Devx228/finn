"""Choose the mock portfolio (spec §4.1) and research set (§4.2) from real recent filings.

Run from the repo root:  api/.venv/Scripts/python scripts/pick_portfolio.py
Uses one NSE announcements request per candidate (the same 120-day window the ingest uses, so
the ingest re-reads it from cache). Writes data/portfolio.json and data/research_set.json.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from finn.push.tagger import is_kmp_change, tag  # noqa: E402
from finn.sources.nse import NSE, is_transcript  # noqa: E402

# Candidate pool from the spec (§4.1), grouped by theme.
POOL = {
    "Banks": ["HDFCBANK", "ICICIBANK", "AUBANK", "IDFCFIRSTB"],
    "NBFC / rural lending": ["BAJFINANCE", "CHOLAFIN", "CREDITACC", "M&MFIN"],
    "IT services": ["INFY", "HCLTECH", "PERSISTENT", "KPITTECH"],
    "Specialty chemicals": ["SRF", "AARTIIND", "DEEPAKNTR", "PIIND", "NAVINFLUOR"],
    "Semiconductors / electronics": ["DIXON", "KAYNES", "CGPOWER", "TATAELXSI"],
    "Consumer": ["HINDUNILVR", "TITAN", "TRENT", "DMART", "VBL"],
    "Pharma / healthcare": ["SUNPHARMA", "DIVISLAB", "APOLLOHOSP"],
    "Industrials / infra": ["LT", "POLYCAB", "ULTRACEMCO", "SUZLON"],
    "Energy / conglomerate / telecom": ["RELIANCE", "BHARTIARTL", "TATASTEEL"],
    "Autos": ["MARUTI", "M&M", "EICHERMOT"],
}
WINDOW_DAYS = 120
SIZE = 18
# Approximate size buckets by market cap (₹ crore). SEBI/AMFI bucket by rank, not value; these
# thresholds approximate the rank cut-offs and are labelled approximate in the UI.
LARGE_CR, MID_CR = 100_000, 30_000


def mcap_crore(symbol: str) -> float | None:
    try:
        import yfinance as yf

        v = yf.Ticker(f"{symbol}.NS").fast_info["marketCap"]
        return round(float(v) / 1e7) if v else None
    except Exception:
        return None
    finally:
        time.sleep(1.0)


def main() -> int:
    nse = NSE()
    master = {s.symbol: s for s in nse.symbols()}
    today = date.today()
    start = today - timedelta(days=WINDOW_DAYS)
    rows = []
    for theme, syms in POOL.items():
        for s in syms:
            if s not in master:
                print(f"  drop {s}: not in NSE symbol master")
                continue
            anns = nse.announcements(s, start, today)
            recent30 = [a for a in anns if a.ts.date() >= today - timedelta(days=30)]
            recent90 = [a for a in anns if a.ts.date() >= today - timedelta(days=90)]
            kmp = [a for a in recent90 if is_kmp_change(a)]
            material = [a for a in recent90 if tag(a) in ("M&A", "capex", "litigation")]
            rows.append(
                {
                    "symbol": s,
                    "name": master[s].name,
                    "theme": theme,
                    "industry": next((a.industry for a in anns if a.industry), None),
                    "filings_120d": len(anns),
                    "results_30d": any(tag(a) == "results" for a in recent30),
                    "kmp_changes_90d": [f"{a.ts:%d %b}: {(a.subject or '')[:110]}" for a in kmp],
                    "material_90d": [f"{a.ts:%d %b} [{tag(a)}]: {(a.subject or '')[:110]}" for a in material],
                    "transcripts_120d": sum(is_transcript(a) for a in anns),
                }
            )
            print(
                f"  {s:11} filings {len(anns):3}  results30 {rows[-1]['results_30d']!s:5} "
                f"kmp {len(kmp)}  material {len(material)}"
            )
    for r in rows:
        r["mcap_cr"] = mcap_crore(r["symbol"])
        m = r["mcap_cr"]
        r["size"] = None if m is None else ("large" if m >= LARGE_CR else "mid" if m >= MID_CR else "small")

    def richness(r):
        return 3 * bool(r["kmp_changes_90d"]) + 2 * bool(r["material_90d"]) + r["results_30d"]

    chosen: list[dict] = []
    per_theme: Counter = Counter()

    def take(r, why):
        if r in chosen or len(chosen) >= SIZE:
            return
        chosen.append(r)
        per_theme[r["theme"]] += 1
        r.setdefault("why", []).append(why)

    ranked = sorted(rows, key=lambda r: (-richness(r), r["symbol"]))
    for r in [r for r in ranked if r["kmp_changes_90d"]][:3]:
        take(r, "real CEO/CFO/MD-level change in the last 90 days")
    for r in [r for r in ranked if r["material_90d"] and r not in chosen][:4]:
        take(r, "real M&A / capex / litigation filing in the last 90 days")
    for theme, why in (
        ("Banks", "bank (financials metric set)"),
        ("NBFC / rural lending", "NBFC (rural lending theme)"),
    ):
        if not any(c["theme"] == theme for c in chosen):
            take(next(r for r in ranked if r["theme"] == theme), why)
    for r in ranked:  # small/mid caps
        if sum(c["size"] in ("small", "mid") for c in chosen) >= 3:
            break
        if r["size"] in ("small", "mid") and per_theme[r["theme"]] < 2:
            take(r, "small/mid cap for size diversity")
    for r in ranked:  # every theme at least once, then richest remaining, max 2 per theme
        if per_theme[r["theme"]] == 0:
            take(r, f"covers theme: {r['theme']}")
    for r in ranked:
        if per_theme[r["theme"]] < 2:
            take(r, "rich recent filing activity")

    checks = {
        "size": len(chosen),
        "kmp_change_companies": sum(bool(c["kmp_changes_90d"]) for c in chosen),
        "material_event_companies": sum(bool(c["material_90d"]) for c in chosen),
        "recent_results_companies": sum(c["results_30d"] for c in chosen),
        "banks": sum(c["theme"] == "Banks" for c in chosen),
        "nbfcs": sum(c["theme"] == "NBFC / rural lending" for c in chosen),
        "small_or_mid": sum(c["size"] in ("small", "mid") for c in chosen),
        "themes": len({c["theme"] for c in chosen}),
    }
    targets = {
        "size": 18,
        "kmp_change_companies": 2,
        "material_event_companies": 3,
        "recent_results_companies": 12,
        "banks": 1,
        "nbfcs": 1,
        "small_or_mid": 2,
    }
    shortfalls = {k: (checks[k], v) for k, v in targets.items() if checks[k] < v}

    # Mock weights (by size) and entry dates — deterministic, labelled synthetic.
    rnd = random.Random(20261112)
    base = {"large": 7.0, "mid": 5.0, "small": 3.0, None: 4.0}
    raw = [base[c["size"]] * rnd.uniform(0.8, 1.2) for c in chosen]
    tot = sum(raw)
    for c, w in zip(chosen, raw, strict=True):
        c["weight_pct"] = round(100 * w / tot, 1)
        c["entry_date"] = str(today - timedelta(days=rnd.randint(90, 3 * 365)))

    # Research set (§4.2): hero with explicit numeric guidance, mid-cap with capex, a financial,
    # and the company with the fewest transcripts (degradation demo).
    by = {r["symbol"]: r for r in rows}
    research = [
        {"symbol": "INFY", "role": "hero: publishes revenue-growth and margin guidance bands"},
    ]
    capex = [r for r in ranked if r["size"] == "mid" and any("[capex]" in m for m in r["material_90d"])]
    research.append(
        {
            "symbol": (capex[0] if capex else by["KAYNES"])["symbol"],
            "role": "mid-cap with capacity / capex guidance",
        }
    )
    research.append(
        {
            "symbol": "CREDITACC" if "CREDITACC" in by else "BAJFINANCE",
            "role": "financial (NBFC): no EBITDA, different statement rows",
        }
    )
    fewest = min(rows, key=lambda r: (r["transcripts_120d"], r["mcap_cr"] or 0))
    research.append(
        {
            "symbol": fewest["symbol"],
            "role": f"fewest concall transcripts in pool ({fewest['transcripts_120d']} "
            f"in 120 days) — degradation demo",
        }
    )

    (ROOT / "data").mkdir(exist_ok=True)
    keep = (
        "symbol",
        "name",
        "theme",
        "industry",
        "size",
        "mcap_cr",
        "weight_pct",
        "entry_date",
        "why",
        "kmp_changes_90d",
        "material_90d",
        "results_30d",
    )
    (ROOT / "data" / "portfolio.json").write_text(
        json.dumps(
            {
                "as_of": str(today),
                "note": "Mock portfolio: real NSE companies, synthetic weights and entry dates.",
                "checks": checks,
                "shortfalls": shortfalls,
                "companies": [{k: c.get(k) for k in keep} for c in chosen],
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (ROOT / "data" / "research_set.json").write_text(
        json.dumps({"as_of": str(today), "companies": research}, indent=1), encoding="utf-8"
    )
    (ROOT / "data" / "candidates.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print("\nchecks:", checks)
    print("shortfalls:", shortfalls or "none")
    print("portfolio:", [c["symbol"] for c in chosen])
    print("research:", [r["symbol"] for r in research])
    print(f"NSE requests: {nse.http.requests_made}, cache hits: {nse.http.cache_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
