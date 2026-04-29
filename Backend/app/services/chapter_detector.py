"""Chapter detection for PDF textbooks.

Strategy (in order):
1. PDF table of contents (`fitz.open(path).get_toc()`) - cheap and reliable
   when the publisher embedded a TOC (most NCERT / state-board books do).
2. Regex fallback over per-page text - matches "Chapter 5", "CHAPTER V",
   "Unit 3", "Lesson 2" headings on the first line of any page.

Returns a list of dicts shaped like ``ChapterInfo`` in
``app.schemas`` (kept dict-shaped here so the detector has no schema
import dependency and can be reused outside the API layer).
"""

from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF

from app.logger import get_logger

logger = get_logger(__name__)


_CHAPTER_PATTERNS = [
    re.compile(
        r"^\s*(?:chapter|chap\.?|unit|lesson)\s+(\d{1,3}|[ivxlcdm]+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(\d{1,3})\s*[\.\)]\s+[A-Z][A-Za-z]"),
]


_ROMAN_MAP = {
    "i": 1, "v": 5, "x": 10, "l": 50,
    "c": 100, "d": 500, "m": 1000,
}


def _roman_to_int(s: str) -> Optional[int]:
    s = s.lower()
    if not all(ch in _ROMAN_MAP for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_MAP[ch]
        total += -val if val < prev else val
        prev = val
    return total or None


def _coerce_number(raw: str) -> Optional[int]:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return _roman_to_int(raw)


def _from_toc(doc: fitz.Document) -> list[dict]:
    """Try the embedded PDF outline. Returns [] if no usable TOC."""
    try:
        toc = doc.get_toc(simple=True) or []
    except Exception as e:
        logger.warning(f"Could not read PDF TOC: {e}")
        return []

    if not toc:
        return []

    top_level = [entry for entry in toc if entry and entry[0] == 1]
    if len(top_level) < 2:
        # Need at least two entries to bracket page ranges meaningfully.
        return []

    chapters: list[dict] = []
    page_count = doc.page_count
    for idx, (_level, title, page) in enumerate(top_level):
        start_page = max(int(page), 1)
        if idx + 1 < len(top_level):
            end_page = max(int(top_level[idx + 1][2]) - 1, start_page)
        else:
            end_page = page_count
        chapters.append(
            {
                "number": idx + 1,
                "title": (title or f"Chapter {idx + 1}").strip(),
                "start_page": start_page,
                "end_page": end_page,
            }
        )
    return chapters


def _from_regex(doc: fitz.Document) -> list[dict]:
    """Walk pages and match chapter-heading regex on the first non-empty line."""
    page_count = doc.page_count
    hits: list[dict] = []

    for page_idx in range(page_count):
        page = doc.load_page(page_idx)
        text = page.get_text("text") or ""
        first_lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:3]
        if not first_lines:
            continue

        for line in first_lines:
            for pattern in _CHAPTER_PATTERNS:
                m = pattern.match(line)
                if not m:
                    continue
                num = _coerce_number(m.group(1))
                if num is None:
                    continue
                title = line.strip()
                hits.append(
                    {
                        "raw_number": num,
                        "title": title,
                        "start_page": page_idx + 1,
                    }
                )
                break
            else:
                continue
            break

    if len(hits) < 2:
        return []

    # Renumber sequentially in case of duplicates / detection noise.
    chapters: list[dict] = []
    for idx, hit in enumerate(hits):
        start_page = hit["start_page"]
        if idx + 1 < len(hits):
            end_page = max(hits[idx + 1]["start_page"] - 1, start_page)
        else:
            end_page = page_count
        chapters.append(
            {
                "number": idx + 1,
                "title": hit["title"],
                "start_page": start_page,
                "end_page": end_page,
            }
        )
    return chapters


def detect_chapters(filepath: str) -> list[dict]:
    """Detect chapters in a PDF.

    Returns ``[]`` if no chapter structure can be inferred (the caller can
    then fall back to treating the whole document as a single "chapter").
    """
    if not filepath.lower().endswith(".pdf"):
        return []

    try:
        with fitz.open(filepath) as doc:
            chapters = _from_toc(doc)
            source = "toc"
            if not chapters:
                chapters = _from_regex(doc)
                source = "regex"
    except Exception as e:
        logger.error(f"Chapter detection failed for '{filepath}': {e}")
        return []

    if chapters:
        logger.info(
            f"Detected {len(chapters)} chapter(s) via {source} in '{filepath}'"
        )
    else:
        logger.info(f"No chapter structure detected in '{filepath}'")
    return chapters
