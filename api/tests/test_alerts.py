"""Alert rules — same fixture and expectations as web/lib/alerts.test.ts."""

import json
from pathlib import Path

from finn.push.alerts import evaluate

DATA = json.loads((Path(__file__).parent / "fixtures" / "alerts_case.json").read_text())


def test_volume_and_price_on_one_day_are_one_alert_flagged_without_disclosure():
    got = evaluate(DATA, DATA["defaults"])
    assert sorted(a["kind"] for a in got) == ["filing", "price"]
    (m,) = [a for a in got if a["kind"] == "price"]
    assert "on volume" in m["text"] and m["no_disclosure"] and m["text"].endswith("moved with no disclosure")


def test_stricter_threshold_fires_fewer():
    r = dict(DATA["defaults"], volume_x=4, move_pct=7)
    assert [a["kind"] for a in evaluate(DATA, r)] == ["filing"]


def test_relative_to_nifty():
    r = dict(DATA["defaults"], vs_nifty=True)
    assert [a["kind"] for a in evaluate(DATA, r)] == ["filing", "volume"]


def test_duplicate_filing_lines_collapse():
    d = dict(DATA, filings=DATA["filings"] + [dict(DATA["filings"][0], id=9)])
    assert len([a for a in evaluate(d, DATA["defaults"]) if a["kind"] == "filing"]) == 1
