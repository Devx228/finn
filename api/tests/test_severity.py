# ruff: noqa: E501  (verbatim filing excerpts)
"""Text-based severity for event filings (ranking fix): no flat score without reading the text."""

from finn.push import severity as sv

CLOSURE = (
    "we wish to inform that the Company has received a Direction from Maharashtra Pollution Control Board "
    "directing closure of manufacturing operations of the Company's unit situated at Plot no. D-2, MIDC, Waluj."
)
PENALTY = "Notice imposing a penalty of Rs.1,60,000 for alleged violation of subscriber verification norms."
ITAT = (
    "The Company has received the Income Tax Appellate Tribunal Order wherein the issues have been majorly "
    "allowed in favour of the Company, having a positive tax impact (including interest) of Rs. 130,000 million "
    "(approx). There is no major impact on financials, operations or other activities of the Company."
)
LT = (
    "Re : L&T bags ( Significant*) order from Noida Metro. *Order Classification Classification Significant Large "
    "Major Mega Ultra-Mega Value in ₹ Cr 1,000 to 2,500 2,500 to 5,000 5,000 to 10,000 10,000 to 15,000 >15,000 "
    "Media Contact"
)
QIP_OPEN = "approved the floor price for the Issue, being ₹ 992.25 per Equity Share"


def test_operational_stop_is_top_tier_whatever_the_category_score():
    s = sv.assess(
        "litigation", None, 34, "regulatory / tax action or order", "Action(s) taken", CLOSURE, 10_000
    )
    assert s is not None and s.base == sv.TOP_BASE and not s.needs_model


def test_small_penalty_scores_low_against_revenue():
    s = sv.assess("litigation", None, 34, "order", "Action(s) taken", PENALTY, 170_000)
    assert s is not None and s.base <= 15 and abs(s.amount_cr - 0.016) < 1e-6  # type: ignore[operator]


def test_company_saying_no_material_impact_caps_the_score():
    s = sv.assess("litigation", None, 34, "order", "Action(s) taken", ITAT, 208_000)
    assert s is not None and s.amount_cr == 13_000 and s.base <= 38 and "no material impact" in s.reason


def test_order_class_uses_the_filings_own_table():
    assert sv.band_from_filing(LT, "") == 1000.0
    s = sv.assess("press_release", "order_win", 38, "order win", "", LT, 300_000)
    assert s is not None and s.amount_cr == 1000.0 and s.base == 36


def test_per_share_price_is_not_the_amount_raised_and_unjudgeable_goes_to_the_model():
    assert sv.stake_amount(QIP_OPEN, "fund_raise") is None
    s = sv.assess("fund_raise", None, 18, "QIP", "", QIP_OPEN, 50_000)
    assert s is not None and s.needs_model


def test_generic_press_release_amounts_are_not_stakes():
    txt = "Cumulative exports since launch are worth Rs 25,288 crore."
    s = sv.assess("press_release", None, 30, "press release", "", txt, 200_000)
    assert s is not None and s.needs_model


def test_empty_summaries_are_recognised():
    for line in [
        "Press release on October 20, 2026",
        "DEEPAK NITRITE LIMITED informed the Exchange about a press release on October 16, 2026.",
        "Outcome of QIP 2026 Special Committee meeting",
        "Action(s) taken or orders passed",
    ]:
        assert sv.says_nothing(line), line
    assert not sv.says_nothing("Pollution board orders Waluj plant shut")
