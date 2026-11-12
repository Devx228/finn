"""Polite HTTP access for exchange sources (owner's access rules, DECISIONS.md 2026-11-12).

- One request at a time per process, at least `min_interval` seconds apart.
- Every response cached on disk by URL. Documents (PDF, XBRL) are cached forever and never
  fetched twice; API listings expire after a TTL.
- Any refusal (401/403/429, an "Access Denied" page or a bot challenge) raises SourceRefused,
  writes a marker file, and blocks every later request until a person reviews and deletes the
  marker. There is no retry around a refusal.
- Transient failures (timeout, 5xx) get exactly one retry after a pause.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from finn.config import REPO_ROOT

USER_AGENT = "FINN-prototype/0.1 (personal non-commercial evaluation project)"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "http"
REFUSED_MARKER = REPO_ROOT / "data" / "cache" / "SOURCE_REFUSED.json"


class SourceRefused(RuntimeError):
    """The source declined our request. Stop; do not work around it."""


@dataclass
class Fetched:
    url: str
    content: bytes
    status: int
    from_cache: bool
    fetched_at: datetime

    def json(self) -> object:
        return json.loads(self.content)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def _looks_refused(r: httpx.Response) -> bool:
    if r.status_code in (401, 403, 429):
        return True
    ctype = r.headers.get("content-type", "")
    if "html" in ctype and r.status_code == 200 and len(r.content) < 4000:
        head = r.text[:2000].lower()
        return any(s in head for s in ("access denied", "captcha", "are you a robot", "blocked"))
    return False


class PoliteClient:
    def __init__(
        self,
        name: str,
        min_interval: float = 1.2,
        cache_dir: Path = CACHE_DIR,
        refused_marker: Path = REFUSED_MARKER,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self.name = name
        self.min_interval = min_interval
        self.cache_dir = cache_dir
        self.refused_marker = refused_marker
        self._lock = threading.Lock()
        self._last = 0.0
        self._sleep = sleep
        self.requests_made = 0
        self.cache_hits = 0
        self._client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            transport=transport,
        )

    # -- cache ---------------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path]:
        h = hashlib.sha256(url.encode()).hexdigest()
        d = self.cache_dir / h[:2]
        return d / f"{h}.bin", d / f"{h}.meta.json"

    def cached(self, url: str, ttl_s: float | None) -> Fetched | None:
        body, meta = self._paths(url)
        if not (body.exists() and meta.exists()):
            return None
        m = json.loads(meta.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(m["fetched_at"])
        if ttl_s is not None and (datetime.now(UTC) - fetched_at).total_seconds() > ttl_s:
            return None
        return Fetched(url, body.read_bytes(), m["status"], True, fetched_at)

    def _store(self, f: Fetched) -> None:
        body, meta = self._paths(f.url)
        body.parent.mkdir(parents=True, exist_ok=True)
        body.write_bytes(f.content)
        meta.write_text(
            json.dumps({"url": f.url, "status": f.status, "fetched_at": f.fetched_at.isoformat()}),
            encoding="utf-8",
        )

    def seed(self, url: str, content: bytes) -> None:
        """Put an already-downloaded document into the cache so it is never fetched again."""
        self._store(Fetched(url, content, 200, False, datetime.now(UTC)))

    # -- fetching ------------------------------------------------------------
    def _check_marker(self) -> None:
        if self.refused_marker.exists():
            raise SourceRefused(
                f"{self.name}: a previous request was refused "
                f"({self.refused_marker.read_text(encoding='utf-8')[:300]}). "
                f"Review, then delete {self.refused_marker} to resume."
            )

    def get(self, url: str, params: dict | None = None, ttl_s: float | None = None) -> Fetched:
        full = str(httpx.URL(url, params=params)) if params else url
        hit = self.cached(full, ttl_s)
        if hit is not None:
            self.cache_hits += 1
            return hit
        self._check_marker()
        with self._lock:
            for attempt in (1, 2):
                wait = self.min_interval - (time.monotonic() - self._last)
                if wait > 0:
                    self._sleep(wait)
                try:
                    r = self._client.get(full)
                    transient = r.status_code >= 500
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    r, transient = None, True
                    err = exc
                finally:
                    self._last = time.monotonic()
                    self.requests_made += 1
                if r is not None and _looks_refused(r):
                    self.refused_marker.parent.mkdir(parents=True, exist_ok=True)
                    note = {
                        "source": self.name,
                        "url": full,
                        "status": r.status_code,
                        "at": datetime.now(UTC).isoformat(),
                        "body_head": r.text[:200],
                    }
                    self.refused_marker.write_text(json.dumps(note, indent=1), encoding="utf-8")
                    raise SourceRefused(f"{self.name} refused {full}: HTTP {r.status_code}")
                if not transient and r is not None:
                    if r.status_code != 200:
                        raise RuntimeError(f"{self.name}: HTTP {r.status_code} for {full}")
                    f = Fetched(full, r.content, r.status_code, False, datetime.now(UTC))
                    self._store(f)
                    return f
                if attempt == 1:
                    self._sleep(max(5.0, self.min_interval * 4))
            detail = f"HTTP {r.status_code}" if r is not None else repr(err)
            raise RuntimeError(f"{self.name}: failed twice for {full}: {detail}")
