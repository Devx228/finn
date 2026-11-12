"""Phase 1 unit tests — offline: fixture XBRL, fake HTTP transport, fake LLM backend."""

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from finn.fin.xbrl import parse_xbrl
from finn.ingest import select_results
from finn.llm import router as rmod
from finn.push.tagger import is_kmp_change, tag
from finn.sources.base import Announcement, ResultsFiling
from finn.sources.http import PoliteClient, SourceRefused

FIX = Path(__file__).parent / "fixtures"
CR = 10**7


# -- XBRL ----------------------------------------------------------------------
def test_xbrl_quarter_and_ytd_are_separate_periods():
    p = parse_xbrl((FIX / "RELIANCE_2024Q4_cons.xml").read_bytes())
    q = (date(2024, 3, 31), date(2024, 1, 1))
    fy = (date(2024, 3, 31), date(2023, 4, 1))
    # NSE declares the YTD context with the quarter's dates; the parser re-dates it.
    assert p.get("RevenueFromOperations", *q) / CR == 240715
    assert p.get("RevenueFromOperations", *fy) / CR == 914472
    assert p.get("ProfitLossForPeriod", *fy) / CR == 79020
    assert p.get("CashFlowsFromUsedInOperatingActivities", *fy) / CR == 158788
    assert p.get("CashFlowsFromUsedInOperatingActivities", *q) is None  # CF only for YTD
    assert p.get("Assets", date(2024, 3, 31)) / CR == 1755986  # instant
    assert p.fmt == "indas"
    assert p.meta["LevelOfRoundingUsedInFinancialStatements"] == "Crores"


def test_xbrl_segments_are_dimensioned_not_plain():
    p = parse_xbrl((FIX / "RELIANCE_2024Q4_cons.xml").read_bytes())
    per_segment = [f for f in p.facts if f.dims.startswith("ReportableSegmentsAxis=")]
    assert len({f.dims for f in per_segment}) >= 5  # RELIANCE reports 5+ segments
    # The plain total stays a plain fact and is not confused with any one segment.
    total = p.get("SegmentRevenueFromOperations", date(2024, 3, 31), date(2024, 1, 1))
    assert total is not None and all(
        f.value < total for f in per_segment if f.concept == "SegmentRevenueFromOperations"
    )


# -- results selection ---------------------------------------------------------
def _rf(end: date, basis: str, filed: int = 1) -> ResultsFiling:
    return ResultsFiling(
        "nse_cfr",
        "X",
        basis,
        "N",
        None,
        end,
        False,
        datetime(2020, 1, filed, tzinfo=UTC),
        f"u/{end}/{basis}/{filed}.xml",
    )


def test_select_prefers_consolidated_and_falls_back_labelled():
    fs = [
        _rf(date(2026, 6, 30), "consolidated"),
        _rf(date(2026, 6, 30), "standalone"),
        _rf(date(2026, 3, 31), "standalone"),
    ]
    got = select_results(fs, today=date(2026, 11, 12))
    assert [(f.period_end, f.basis) for f in got] == [
        (date(2026, 3, 31), "standalone"),
        (date(2026, 6, 30), "consolidated"),
    ]


def test_select_keeps_recent_quarters_and_old_half_years_only():
    # today 12 Nov 2026: quarters from ~Nov 2022, half-years (Mar/Sep) from ~Oct 2016.
    ends = [
        date(2016, 9, 30),
        date(2017, 3, 31),
        date(2017, 6, 30),
        date(2022, 6, 30),
        date(2023, 6, 30),
        date(2026, 6, 30),
    ]
    got = {
        f.period_end for f in select_results([_rf(e, "consolidated") for e in ends], today=date(2026, 11, 12))
    }
    assert got == {date(2017, 3, 31), date(2023, 6, 30), date(2026, 6, 30)}


def test_select_latest_revision_wins():
    fs = [_rf(date(2026, 6, 30), "consolidated", 1), _rf(date(2026, 6, 30), "consolidated", 9)]
    (only,) = select_results(fs, today=date(2026, 11, 12))
    assert only.xbrl_url.endswith("/9.xml")


# -- tagger --------------------------------------------------------------------
def _a(cat: str, subj: str) -> Announcement:
    return Announcement("1", "X", datetime(2026, 11, 1, tzinfo=UTC), cat, subj, None, None, None, {})


@pytest.mark.parametrize(
    ("cat", "subj", "want"),
    [
        ("Outcome of Board Meeting", "approved the financial results for the quarter", "results"),
        ("Acquisition", "acquisition of 51% stake in ABC", "M&A"),
        ("Updates", "Commissioning of cement capacity at Unit 3", "capex"),
        ("Action(s) taken or orders passed", "GST order", "litigation"),
        ("Copy of Newspaper Publication", "newspaper advertisement", "other"),
    ],
)
def test_tagger_categories(cat, subj, want):
    assert tag(_a(cat, subj)) == want


def test_kmp_change_needs_a_top_role():
    assert is_kmp_change(_a("Updates", "Resignation of Mr X as Chief Financial Officer"))
    assert not is_kmp_change(_a("Updates", "Appointment of statutory auditor"))


# -- polite client -------------------------------------------------------------
def _client(tmp_path, handler, sleeps):
    return PoliteClient(
        "T",
        min_interval=1.2,
        cache_dir=tmp_path / "c",
        refused_marker=tmp_path / "REFUSED.json",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )


def test_polite_client_caches_and_spaces_requests(tmp_path):
    hits = []
    sleeps: list[float] = []
    c = _client(tmp_path, lambda r: (hits.append(str(r.url)), httpx.Response(200, content=b"ok"))[1], sleeps)
    c.get("https://x/a")
    c.get("https://x/b")
    assert c.get("https://x/a").from_cache  # never fetched twice
    assert len(hits) == 2 and c.requests_made == 2
    assert sleeps and 0 < sleeps[0] <= 1.2  # second request waited


def test_polite_client_stops_on_refusal_and_stays_stopped(tmp_path):
    sleeps: list[float] = []
    c = _client(tmp_path, lambda r: httpx.Response(403, text="Access Denied"), sleeps)
    with pytest.raises(SourceRefused):
        c.get("https://x/a")
    assert (tmp_path / "REFUSED.json").exists()
    c2 = _client(tmp_path, lambda r: httpx.Response(200, content=b"ok"), sleeps)
    with pytest.raises(SourceRefused):  # marker blocks later runs until a person clears it
        c2.get("https://x/other")


def test_polite_client_detects_access_denied_page_with_200(tmp_path):
    c = _client(
        tmp_path,
        lambda r: httpx.Response(
            200, headers={"content-type": "text/html"}, text="<html>Access Denied</html>"
        ),
        [],
    )
    with pytest.raises(SourceRefused):
        c.get("https://x/a")


# -- router --------------------------------------------------------------------
class Out(BaseModel):
    label: str


class FakeBackend:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, route, messages, schema, timeout):
        self.calls.append(route)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step, 10, 2


class MemStore:
    def __init__(self):
        self.cache, self.ledger = {}, []

    def cache_get(self, k):
        return self.cache.get(k)

    def cache_put(self, k, tier, provider, model, response):
        self.cache[k] = {"provider": provider, "model": model, "response": response}

    def log(self, **kw):
        self.ledger.append(kw)


@pytest.fixture
def two_routes(monkeypatch):
    monkeypatch.setenv("LLM_TIER_BULK", "ollama:a,ollama:b")
    monkeypatch.setenv("LLM_RPM_OLLAMA", "0")


def test_router_repairs_invalid_json_then_caches(two_routes):
    be, st = FakeBackend(["not json", '{"label": "x"}']), MemStore()
    r = rmod.Router(backend=be, store=st, sleep=lambda s: None)
    got = r.call("BULK", "t", "v1", "sys", "u", Out)
    assert got.data.label == "x" and not got.cache_hit and len(be.calls) == 2
    again = r.call("BULK", "t", "v1", "sys", "u", Out)
    assert again.cache_hit and len(be.calls) == 2  # never asked twice
    assert [e["ok"] for e in st.ledger] == [False, True, True]


def test_router_falls_back_on_429(two_routes):
    be = FakeBackend([rmod.RetryableError("429"), '{"label": "y"}'])
    got = rmod.Router(backend=be, store=MemStore(), sleep=lambda s: None).call(
        "BULK", "t", "v1", "s", "u", Out
    )
    assert got.data.label == "y" and [c.model for c in be.calls] == ["a", "b"]


def test_router_skips_providers_without_keys(monkeypatch):
    monkeypatch.setenv("LLM_TIER_REASON", "groq:some-model")
    monkeypatch.setattr(rmod, "provider_available", lambda p: p == "ollama")
    with pytest.raises(rmod.LLMUnavailable):
        rmod.Router(backend=FakeBackend([]), sleep=lambda s: None).call("REASON", "t", "v1", "s", "u", Out)
