"""Pull side: guidance rules and promised-vs-delivered verdicts (no DB, no model)."""

from datetime import date

from finn.pull.guidance import Item, doubt, rule_items, sentences
from finn.pull.research import cc_reported, tracks, verdict


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


def test_number_before_metric_and_increments():
    got = _items(
        "The preliminary outlook for FY26 projects healthy 18%-20% AUM growth, 4.2%-4.5% ROA and 17%-19% ROE."
    )
    by = {i["metric"]: (i["low"], i["high"]) for i in got}
    assert by == {"aum_growth": (18.0, 20.0), "roa": (4.2, 4.5), "roe": (17.0, 19.0)}
    assert not _items("Due to this delay, we expect additional 40-50 bps credit cost in FY26.")


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


CC_CALLS = [
    {
        "qend": date(2026, 3, 31),
        "label": "Q4 FY26 call",
        "url": "q4",
        "pages": [
            "We had growth of 3.1% for the full year in constant currency terms. Momentum in Financial "
            "Services continues with 3.9% year-on-year growth in constant currency terms."
        ],
    },
    {
        "qend": date(2026, 9, 30),
        "label": "Q2 FY27 call",
        "url": "q2",
        "pages": [
            "Our revenue growth for Q2 was 1.5% YoY and 1.2% sequentially in constant currency terms. "
            "H1 revenue growth was at 1.9% in constant currency terms and 2.1% in reported terms."
        ],
    },
]


def test_cc_growth_is_read_from_the_companys_own_words():
    got = {(r["fy"], r["quarters"]): (r["value"], r["url"]) for r in cc_reported(CC_CALLS, 4)}
    assert got == {(2026, 4): (3.1, "q4"), (2027, 2): (1.9, "q2")}  # not the segment, not sequential


def test_cc_guidance_chain_resolves_against_company_reported_cc():
    calls = [
        _call("Q4", "2026-04-27", 1.5, 3.5),
        _call("Q1", "2026-07-28", 1.5, 3.0),
        _call("Q2", "2026-10-28", 1.0, 2.0),
    ]
    qs = [{"fy": 2027, "label": f"Q{i} FY27", "revenue": 110.0, "end": f"2026-0{3 * i}-30"} for i in (1, 2)]
    qs += [{"fy": 2026, "label": f"Q{i} FY26", "revenue": 100.0, "end": f"2025-0{3 * i}-30"} for i in (1, 2)]
    for q in qs:
        q["xbrl"] = None
    (t,) = tracks(calls, qs, 4, cc=cc_reported(CC_CALLS, 4))
    assert [p["change"] for p in t["points"]] == ["first given", "cut", "cut"]
    assert t["verdict"] == "on track" and t["actual"]["basis"] == "company-reported, constant currency"
    assert t["actual"]["source"]["url"] == "q2" and t["story"].endswith("→ on track.")


def test_sentence_over_a_page_break_keeps_its_subject():
    pages = [
        "We have committed a full year revenue of totally INR500 crores between both,",
        "Kaynes Technology India Limited August 08, 2026 Page 14 of 19 INR450 to INR500 crores, which "
        "is what we are targeting at this point in time.",
    ]
    (s,) = [s for _, s in sentences(pages) if "targeting" in s]
    assert s.startswith("We have committed") and "Page 14" not in s and "Kaynes" not in s


def test_segment_rupee_targets_and_open_ended_aspirations_are_not_company_guidance():
    (seg,) = _items("We said we will be funding capex this year of about INR300 crores for the PCB business.")
    assert seg["scope"] == "segment"
    (asp,) = _items(
        "We will optimize margins over a period of time and deliver our aspirational goals of 16 to 17%."
    )
    assert asp["period"] == "medium term"
    assert not _items("But if we look at the year on year growth, on TCV it was just 4%, we expect more.")


def test_strict_check_drops_a_mislabelled_model_item():
    q = "We raised our profitability guidance for FY27, ROA of 5.2% to 5.8% versus 4% to 4.8% earlier."
    bad = Item(metric="pat_growth", label="x", low=5.2, high=5.8, unit="%", confidence="high", quote=q)
    assert doubt(bad) == "metric not named in the quote"
    ok = Item(
        metric="operating_margin",
        label="x",
        low=20,
        high=22,
        unit="%",
        confidence="high",
        quote="Our operating margin guidance for FY27 is 20% to 22%.",
    )
    assert doubt(ok) is None


def test_analyst_restating_guidance_is_not_management():
    from finn.pull.guidance import select

    pages = [
        "Moderator: Next question comes from line of Shreepal Doshi from Equirus. Please go ahead. "
        "Shreepal Doshi: Okay, we have given a guidance of 5.5-6.0% credit cost for FY26. "
        "Ganesh Narayanan: We expect credit cost of 5.5% to 6% for FY26, and we will hold it."
    ]
    _, chosen = select(pages)
    assert [s for _, s in chosen] == [
        "Ganesh Narayanan: We expect credit cost of 5.5% to 6% for FY26, and we will hold it."
    ]
