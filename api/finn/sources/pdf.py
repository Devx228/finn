"""PDF → per-page text with PyMuPDF. Text is what we keep; the PDF itself is never re-hosted."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pymupdf

# A page with fewer extractable characters than this is treated as image-only.
SCANNED_CHARS_PER_PAGE = 40


@dataclass
class PdfText:
    sha256: str
    pages: list[str]
    is_scanned: bool

    @property
    def n_pages(self) -> int:
        return len(self.pages)


def extract(content: bytes, max_pages: int | None = None) -> PdfText:
    sha = hashlib.sha256(content).hexdigest()
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        n = len(doc) if max_pages is None else min(len(doc), max_pages)
        pages = [doc[i].get_text("text").replace("\x00", "") for i in range(n)]
    chars = sum(len(p.strip()) for p in pages)
    scanned = bool(pages) and chars < SCANNED_CHARS_PER_PAGE * len(pages)
    return PdfText(sha256=sha, pages=pages, is_scanned=scanned)
