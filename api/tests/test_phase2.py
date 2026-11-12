"""Phase 2 unit tests — results arithmetic, tiers, bundling, rules, text helpers. Offline."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

from finn.push import brief
from finn.push.classify_llm import clip_words, salient, thin_subject
from finn.push.classify_rules import classify
from finn.push.results import Period, build, fiscal_label, metrics, pct, validate

CR = D(10**7)


def indas(rev, oi, exp, fc, da, pbt, pat, exc=D(0)):
    pbe = pbt - exc
    return {
        "RevenueFromOperations": rev * CR,
        "OtherIncome": oi * CR,
        "Income": (rev + oi) * CR,
        "Expenses": exp * CR,
        "FinanceCosts": fc * CR,
        "DepreciationDepletionAndAmortisationExpense": da * CR,
        "ProfitBeforeExceptionalItemsAndTax": pbe * CR,
        "ExceptionalItemsBeforeTax": exc * CR,
        "ProfitBeforeTax": pbt * CR,
        "ProfitLossForPeriod": pat * CR,
    }


def test_ebitda_formula_excludes_other_income():
    f = indas(rev=D(1000), oi=D(50), exp=D(850), fc=D(20), da=D(30), pbt=D(200), pat=D(150))
    m = metrics("indas", f)
    assert m["ebitda"] / CR == 200 + 20 + 30 - 50  # 200


def test_validation_passes_when_identities_hold_and_flags_when_not():
    good = indas(rev=D(1000), oi=D(50), exp=D(850), fc=D(20), da=D(30), pbt=D(200), pat=D(150))
    assert validate("indas", good) == []
    bad = dict(good, Expenses=D(700) * CR)  # income − expenses no longer equals PBT
    assert any("income − expenses" in i for i in validate("indas", bad))


def test_bank_metric_set_has_no_ebitda():
    f = {
        "InterestEarned": D(100) * CR,
        "InterestExpended": D(60) * CR,
        "Income": D(130) * CR,
        "ExpenditureExcludingProvisionsAndContingencies": D(80) * CR,
        "ProvisionsOtherThanTaxAndContingencies": D(10) * CR,
        "ExceptionalItems": D(0),
        "OperatingProfitBeforeProvisionAndContingencies": D(50) * CR,
        "ProfitLossFromOrdinaryActivitiesBeforeTax": D(40) * CR,
        "ProfitLossForThePeriod": D(30) * CR,
    }
    m = metrics("bank", f)
    assert "ebitda" not in m and m["nii"] / CR == 40
    assert validate("bank", f) == []


def test_qoq_yoy_same_basis_only_and_loss_base():
    cur = Period(
        date(2026, 9, 30), "consolidated", indas(D(1100), D(50), D(900), D(20), D(30), D(250), D(180)), "u"
    )
    q = Period(
        date(2026, 6, 30), "consolidated", indas(D(1000), D(50), D(850), D(20), D(30), D(200), D(150)), "u"
    )
    y = Period(
        date(2025, 9, 30), "standalone", indas(D(900), D(50), D(780), D(20), D(30), D(170), D(120)), "u"
    )
    card = build("indas", cur, q, y)
    rev = next(r for r in card.rows if r["metric"] == "revenue")
    assert rev["qoq_pct"] == 10.0 and rev["yoy_pct"] is None  # no splice across basis
    assert "YoY omitted" in (card.basis_note or "")
    assert pct(D(5), D(-10)) is None and pct(D(5), D(0)) is None  # % vs a loss base is meaningless
    assert len(card.take.split()) <= 20


def test_fiscal_labels():
    assert fiscal_label(date(2026, 9, 30), 4) == "Q2 FY27"
    assert fiscal_label(date(2026, 3, 31), 4) == "Q4 FY26"
    assert fiscal_label(date(2026, 9, 30), 1) == "Q3 CY26"  # calendar-year filer (e.g. VBL)


def _item(i, score, cat="results", st="results_filing", hours=0):
    t = datetime(2026, 10, 30, 12, tzinfo=UTC) + timedelta(hours=hours)
    it = brief.Item(f"f{i}", 1, "X", "X Ltd", t, cat, st, 0, [i], "h", None, None)
    it.score = score
    return it


def test_now_tier_is_capped_and_thresholds_hold():
    items = [_item(i, s) for i, s in enumerate([95, 90, 88, 80, 75, 71, 70, 55, 39])]
    t = brief.tiers(items)
    assert len(t["now"]) == 5 and min(i.score for i in t["now"]) >= 75
    assert [i.score for i in t["worth"]] == [71, 70, 55]  # cap pushes the rest down a tier
    assert [i.score for i in t["buried"]] == [39]


def test_results_family_bundles_into_one_item():
    items = [
        _item(1, 0),
        _item(2, 0, "earnings_call", "call_notice", hours=2),
        _item(3, 0, "unclassified", "newspaper_copy", hours=20),
        _item(4, 0, "unclassified", "newspaper_copy", hours=60),
    ]  # outside 36 h
    out = brief.bundle_results(items)
    assert [i.id for i in out] == ["f1", "f4"] and out[0].filing_ids == [1, 2, 3]


def test_rules_examples():
    assert classify("Trading Window", "closure").category == "unclassified"
    c = classify("Outcome of Board Meeting", "X has submitted the financial results for Sep 2026")
    assert (c.category, c.sub_type) == ("results", "results_filing")
    c = classify("Disclosure under SEBI Takeover Regulations", "Regulation 31(4) encumbrance")
    assert c.category == "pledging"
    c = classify(
        "General Updates",
        "X informed the Exchange about General Updates",
        "Letterhead ... Sub: Resignation of Mr A as Chief Financial Officer ...",
    )
    assert (c.category, c.sub_type) == ("management_change", "kmp_change")
    c = classify("Change in Auditors", "resignation of statutory auditor")
    assert c.sub_type == "auditor_resignation" and c.base >= 60  # promoted


def test_text_helpers():
    assert salient("ADDRESS Mumbai 400001 Sub: Capex approval") == "Sub: Capex approval"
    assert thin_subject("X Limited has informed the Exchange about General Updates")
    assert not thin_subject("X Limited has informed the Exchange regarding 'Acquisition of Y'")
    assert clip_words(" ".join(["w"] * 30)).count("w") == 18
