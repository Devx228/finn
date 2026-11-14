"""Network scoring (spec §9): pure functions, no DB."""

from datetime import date

from finn.network.graph import Edu, Emp, Person, label, overlap, paths, warmth, who
from finn.network.service import org_theme


def _p(pid, name, emps=(), edus=(), **rel):
    return Person(pid, name, "contact", True, list(emps), list(edus), **rel)


def test_warmth_recent_close_contact_is_strong_and_cold_is_weak():
    hot = _p(
        1,
        "A",
        how_known="ex-colleague",
        since=date(2015, 1, 1),
        last_contact=date(2026, 10, 1),
        interactions_24m=8,
        closeness=5,
    )
    cold = _p(
        2,
        "B",
        how_known="classmate",
        since=date(2024, 1, 1),
        last_contact=date(2024, 6, 1),
        interactions_24m=0,
        closeness=1,
    )
    assert label(warmth(hot)[0]) == "strong"
    assert label(warmth(cold)[0]) == "weak"
    assert warmth(_p(3, "C"))[0] == 0.0


def test_overlap_needs_shared_years_at_same_org():
    a = _p(1, "A", [Emp(10, "ICICI Bank", "SVP", "finance", 4, date(2010, 1, 1), date(2014, 1, 1))])
    b = _p(2, "B", [Emp(10, "ICICI Bank", "ED", "finance", 4, date(2012, 1, 1), None)])
    c = _p(3, "C", [Emp(10, "ICICI Bank", "ED", "finance", 4, date(2015, 1, 1), None)])
    s, ev = overlap(a, b)
    assert s > 0.3 and "ICICI Bank" in ev[0]
    assert overlap(a, c)[0] == 0  # same org, different years


def test_classmates_score_from_education():
    a = _p(1, "A", edus=[Edu(5, "IIM Ahmedabad", "MBA", 2008)])
    b = _p(2, "B", edus=[Edu(5, "IIM Ahmedabad", "MBA", 2009)])
    assert overlap(a, b)[0] == 0.5


def test_paths_rank_by_warmth_times_overlap():
    target = Person(
        9, "Target", "public_figure", False, [Emp(10, "ICICI Bank", None, None, None, date(2000, 1, 1), None)]
    )
    job = [Emp(10, "ICICI Bank", "VP", "finance", 4, date(2010, 1, 1), date(2015, 1, 1))]
    warm = _p(
        1,
        "Warm",
        job,
        how_known="ex-colleague",
        since=date(2012, 1, 1),
        last_contact=date(2026, 11, 1),
        interactions_24m=8,
        closeness=5,
    )
    cool = _p(
        2,
        "Cool",
        job,
        how_known="classmate",
        since=date(2012, 1, 1),
        last_contact=date(2024, 1, 1),
        interactions_24m=1,
        closeness=2,
    )
    ps = paths(target, [cool, warm])
    assert [p.contact.name for p in ps] == ["Warm", "Cool"]
    assert "You → Warm" in ps[0].sentence


def test_who_flags_current_employees_and_prefers_former():
    rel = dict(
        how_known="ex-colleague",
        since=date(2015, 1, 1),
        last_contact=date(2026, 10, 1),
        interactions_24m=5,
        closeness=4,
    )
    current = _p(1, "Now", [Emp(10, "Co", "CFO", "finance", 5, date(2015, 1, 1), None)], **rel)
    former = _p(2, "Was", [Emp(10, "Co", "CFO", "finance", 5, date(2015, 1, 1), date(2025, 6, 1))], **rel)
    current.closeness = 5
    current.interactions_24m = 12
    out = who(10, set(), set(), [current, former], "results", "Co")
    assert out[0].person.name == "Was"
    flagged = next(c for c in out if c.person.name == "Now")
    assert flagged.compliance and "insider" in flagged.compliance


def test_org_theme_matches_legal_name_variants():
    assert org_theme("ICICI Bank Limited", None) == "banking"
    assert org_theme("Infosys Limited", None) == "IT services"
    assert org_theme("Some Unknown Co", None) is None


def test_filing_bio_spans_are_never_invented():
    """'A member of the ICICI Group since 1992' doesn't put someone at ICICI Bank in 1992; an open
    span closes at the next stated employer; no end year is ever made up."""
    from datetime import date

    from finn.network.graph import Emp, Person
    from finn.network.service import _career_json, clean_public_careers

    bio = (
        "A member of the ICICI Group since 1992, he has built a career spanning treasury, retail banking. "
        "He has held positions including Executive Director of ICICI Bank. "
        "Mr. Bagchi served as Executive Director of ICICI Bank from 2017 to 2023. "
        "Since June 2023, Mr. Bagchi has been serving as MD & CEO of ICICI Prudential Life Insurance."
    )

    class Conn:
        def execute(self, *_a, **_k):
            class R:
                def fetchall(self):
                    return [(1, [bio], 99)]

            return R()

    p = Person(
        7,
        "Anup Bagchi",
        "public_figure",
        False,
        emps=[
            Emp(1, "ICICI Bank Limited", "various positions", None, None, date(1992, 1, 1), None),
            Emp(
                1, "ICICI Bank Limited", "Executive Director", None, None, date(2017, 1, 1), date(2023, 12, 1)
            ),
            Emp(2, "ICICI Prudential Life Insurance", "MD & CEO", None, None, date(2023, 6, 1), None),
            Emp(99, "HDFC Bank Limited", "MD & CEO", None, None, date(2026, 10, 1), None),
        ],
    )
    clean_public_careers(Conn(), {7: p}, {7: [{"filing_id": 1}]})  # type: ignore[arg-type]
    spans = [(c["org"], c["span"]) for c in _career_json(p)]
    assert ("ICICI Bank Limited", "years not stated") in spans  # named, but no year for the bank
    assert ("ICICI Bank Limited", "2017–2023") in spans
    assert ("ICICI Prudential Life Insurance", "2023–2026") in spans  # closed at the next employer
    assert ("HDFC Bank Limited", "from 2026") in spans  # no "now"
    assert not any("1992" in s for _, s in spans)
