"""Pull side: guidance rules and promised-vs-delivered verdicts (no DB, no model)."""

from finn.pull.guidance import rule_items
from finn.pull.research import tracks, verdict


def _items(*sentences: str, fy: int = 2027) -> list[dict]:
    return rule_items([(1, s) for s in sentences], fy)


def test_multi_metric_sentence_splits_each_band():
    got = _items(
        "For FY27, we are guiding an AUM growth of 20.0-25.0%, NIM of 12.8-13.2%, cost to income of "
        "33.0-35.0%, credit cost of 3.0-4.0%, ROA of 4.0-4.8%, and an ROE of 16.0-20.0%."
    )
    by = {i["metric"]: (i["low"], i["high"]) for i in got}
    assert by["aum_growth"] == (20.0, 25.0)
    assert by["nim"] == (12.8, 13.2)
    assert by["credit_cost"] == (3.0, 4.0)
    assert by["roe"] == (16.0, 20.0)
    assert "revenue_growth" not in by
    assert all(i["period"] == "FY27" for i in got)


def test_revision_takes_the_new_band():
    got = _items("We are revising our full year revenue growth guidance from 1.5% to 3% to 1% to 2%.")
    assert [(i["metric"], i["low"], i["high"]) for i in got][-1] == ("revenue_growth", 1.0, 2.0)


def test_questions_outcomes_and_segments_are_not_guidance():
    assert not _items("And growth also confident of holding it in the range of 20% to 25%?")
    assert not _items("Our credit cost ended at 6.74% as against the guidance of 5.5% to 6.0%.")
    assert not _items("You had shared that this FY27 credit cost guidance of 4.0% to 4.5% is factored in.")
    assert not _items("As we said, the microfinance growth being in the range of 10-12%.")


def test_verdicts():
    assert verdict({"value": 21.0}, 20, 22, final=False)[0] == "on track"
    assert verdict({"value": 12.9}, 17, 17, final=True)[0] == "missed"
    assert verdict(None, 20, 22, final=True)[0] == "unverifiable"


def _call(label, date, low, high):
    return {
        "label": label,
        "filed_at": date,
        "url": "u",
        "items": [
            {
                "metric": "revenue_growth",
                "period": "FY27",
                "low": low,
                "high": high,
                "unit": "%",
                "quote": "revenue growth guidance in constant currency",
                "by": "rules",
            }
        ],
    }


def test_band_changes_are_computed_and_cc_is_not_compared_with_rupees():
    calls = [
        _call("Q4", "2026-04-27", 1.5, 3.5),
        _call("Q1", "2026-07-28", 1.5, 3.0),
        _call("Q2", "2026-10-28", 1.0, 2.0),
    ]
    qs = [{"fy": 2027, "label": f"Q{i} FY27", "revenue": 110.0, "end": f"2026-0{3 * i}-30"} for i in (1, 2)]
    qs += [{"fy": 2026, "label": f"Q{i} FY26", "revenue": 100.0, "end": f"2025-0{3 * i}-30"} for i in (1, 2)]
    (t,) = tracks(calls, qs, 4)
    assert [p["change"] for p in t["points"]] == ["first given", "cut", "cut"]
    assert t["verdict"] == "not comparable"
