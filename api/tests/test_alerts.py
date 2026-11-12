"""Alert rules — same fixture and expectations as web/lib/alerts.test.ts."""

import json
from pathlib import Path

from finn.push.alerts import evaluate

DATA = json.loads((Path(__file__).parent / "fixtures" / "alerts_case.json").read_text())


def test_defaults_fire_volume_price_and_category():
    assert sorted(a["kind"] for a in evaluate(DATA, DATA["defaults"])) == ["filing", "price", "volume"]


def test_stricter_threshold_fires_fewer():
    r = dict(DATA["defaults"], volume_x=4, move_pct=7)
    assert [a["kind"] for a in evaluate(DATA, r)] == ["filing"]


def test_relative_to_nifty():
    r = dict(DATA["defaults"], vs_nifty=True)
    assert not [a for a in evaluate(DATA, r) if a["kind"] == "price"]
