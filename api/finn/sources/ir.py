"""Earnings-call transcripts from a company's own investor-relations site (owner's rules, 13 Nov):

- robots.txt is read first and respected (a fetch it disallows is never made);
- one plain request per file (honest User-Agent, no header tricks, no retries), >= 5 s apart;
- every file is cached in data/ir/<SYMBOL>/ and listed in its manifest.json (original URL kept
  for the citation; PDFs are gitignored, never re-hosted);
- the first refusal (401/403/429, an "access denied"/bot page, or anything that isn't a PDF)
  writes data/cache/IR_REFUSED_<host>.json and that host is never contacted again.
"""

from __future__ import annotations

import json
import time
import urllib.robotparser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from finn.config import REPO_ROOT
from finn.sources.http import USER_AGENT

IR_DIR = REPO_ROOT / "data" / "ir"
MARKERS = REPO_ROOT / "data" / "cache"
GAP_S = 5.0
SOURCE = "company IR site"


class HostRefused(RuntimeError):
    pass


def _marker(host: str) -> Path:
    return MARKERS / f"IR_REFUSED_{host}.json"


class IRFetcher:
    def __init__(self, client: httpx.Client | None = None, sleep=time.sleep) -> None:
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        )
        self.sleep = sleep
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last = 0.0
        self.requests = 0

    def _wait(self) -> None:
        gap = GAP_S - (time.monotonic() - self._last)
        if gap > 0:
            self.sleep(gap)
        self._last = time.monotonic()

    def _refuse(self, host: str, url: str, why: str) -> None:
        MARKERS.mkdir(parents=True, exist_ok=True)
        note = {"host": host, "url": url, "why": why, "at": datetime.now(UTC).isoformat()}
        _marker(host).write_text(json.dumps(note, indent=1), encoding="utf-8")
        raise HostRefused(f"{host} refused {url}: {why}")

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        host = u.netloc
        if _marker(host).exists():
            raise HostRefused(f"{host} refused us before ({_marker(host).name}); not contacting it again")
        if host not in self._robots:
            self._wait()
            self.requests += 1
            r = self.client.get(f"{u.scheme}://{host}/robots.txt")
            if r.status_code in (401, 403, 429):
                self._robots[host] = None
                self._refuse(host, f"{u.scheme}://{host}/robots.txt", f"HTTP {r.status_code}")
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(r.text.splitlines() if r.status_code == 200 else [])  # no robots.txt = allowed
            self._robots[host] = parser
        rp = self._robots[host]
        return bool(rp and rp.can_fetch(USER_AGENT, url))

    def fetch(self, symbol: str, url: str, file: str, call_date: str, quarter: str) -> str:
        """Fetch one transcript into data/ir/<symbol>/<file> (cached) and record it in the manifest."""
        folder = IR_DIR / symbol
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / file
        if not dest.exists():
            if not self.allowed(url):
                return f"{quarter}: robots.txt disallows {url}; not fetched"
            host = urlparse(url).netloc
            self._wait()
            self.requests += 1
            r = self.client.get(url)
            body = r.content
            if r.status_code in (401, 403, 429):
                self._refuse(host, url, f"HTTP {r.status_code}")
            if r.status_code == 404:
                return f"{quarter}: 404 at {url}"
            if r.status_code != 200 or not body.startswith(b"%PDF"):
                head = body[:300].decode("utf-8", "replace").lower()
                if any(s in head for s in ("access denied", "captcha", "robot", "blocked", "forbidden")):
                    self._refuse(host, url, "access-denied page")
                return f"{quarter}: not a PDF (HTTP {r.status_code}) at {url}"
            dest.write_bytes(body)
        man_p = folder / "manifest.json"
        man: dict = (
            json.loads(man_p.read_text(encoding="utf-8"))
            if man_p.exists()
            else {"symbol": symbol, "source": SOURCE, "calls": []}
        )
        man["calls"] = [c for c in man["calls"] if c["file"] != file] + [
            {"file": file, "url": url, "call_date": call_date, "quarter": quarter}
        ]
        man_p.write_text(json.dumps(man, indent=1), encoding="utf-8")
        return f"{quarter}: ok ({dest.stat().st_size // 1024} KB)"


def links(
    f: IRFetcher, page_url: str, pattern: str = r"transcript|concall|con-call|earnings?.?call"
) -> list[str]:
    """PDF links on one IR listing page (robots.txt respected; one request; refusal is final)."""
    import re
    from urllib.parse import urljoin

    if not f.allowed(page_url):
        return []
    host = urlparse(page_url).netloc
    f._wait()
    f.requests += 1
    r = f.client.get(page_url)
    if r.status_code in (401, 403, 429):
        f._refuse(host, page_url, f"HTTP {r.status_code}")
    if r.status_code != 200:
        return []
    if "access denied" in r.text[:600].lower():
        f._refuse(host, page_url, "access-denied page")
    hrefs = re.findall(r"""href\s*=\s*["']([^"']+?\.pdf)["']""", r.text, re.I)
    out = []
    for h in hrefs:
        u = urljoin(page_url, h.replace(" ", "%20"))
        if re.search(pattern, u, re.I) and u not in out:
            out.append(u)
    return out
