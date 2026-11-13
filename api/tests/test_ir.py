"""Company IR fetcher: robots.txt respected, first refusal is final, no retries."""

import httpx
import pytest

from finn.sources import ir


def _fetcher(tmp_path, monkeypatch, handler):
    monkeypatch.setattr(ir, "IR_DIR", tmp_path / "ir")
    monkeypatch.setattr(ir, "MARKERS", tmp_path / "cache")
    calls = []

    def h(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return handler(req)

    return ir.IRFetcher(client=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None), calls


def test_robots_disallow_means_no_request(tmp_path, monkeypatch):
    f, calls = _fetcher(
        tmp_path,
        monkeypatch,
        lambda r: (
            httpx.Response(200, text="User-agent: *\nDisallow: /docs/")
            if r.url.path == "/robots.txt"
            else httpx.Response(200, content=b"%PDF-1.7")
        ),
    )
    out = f.fetch("X", "https://co.example/docs/t.pdf", "t.pdf", "2025-01-01", "Q3 FY25")
    assert "robots.txt disallows" in out and calls == ["https://co.example/robots.txt"]


def test_first_refusal_stops_the_host_for_good(tmp_path, monkeypatch):
    f, calls = _fetcher(
        tmp_path,
        monkeypatch,
        lambda r: (
            httpx.Response(404) if r.url.path == "/robots.txt" else httpx.Response(403, text="Access Denied")
        ),
    )
    with pytest.raises(ir.HostRefused):
        f.fetch("X", "https://co.example/a.pdf", "a.pdf", "2025-01-01", "Q3 FY25")
    n = len(calls)
    with pytest.raises(ir.HostRefused):
        ir.IRFetcher(client=f.client, sleep=lambda s: None).fetch(
            "X", "https://co.example/b.pdf", "b.pdf", "x", "y"
        )
    assert len(calls) == n  # nothing sent after the refusal, even by a new fetcher
