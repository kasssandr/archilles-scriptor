"""The PDF outline: chapter titles the document's catalogue states.

The outline names each chapter and the physical page it starts on — exactly
the pages where text heuristics must guess: a chapter opening shows no running
head, only the big chapter number, and the title is glued to the first
paragraph. It also identifies chapter running heads, whose trailing year
("… in 759") the edge-number preservation in ``running_elements`` would
otherwise keep as a phantom page number.

Believing an outline is a two-step decision, mirroring the page-label rule:
``credible`` filters mechanically generated junk document-wide (rules adapted
from Archilles ``pdf_extractor._build_page_toc_map``), and even a credible
entry only acts where the page itself shows the title. Matching is
OCR-tolerant: it compares only the letters and digits, case-folded, and
accepts a small edit distance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

OUTLINE_FILENAME = "outline.json"

# Scanner artifacts posing as outline titles (Archilles `_JUNK_TOC_RE`).
_JUNK_TITLE_RE = re.compile(r"^(scan\s*\d+|z\s*-\s*|page\s*\d+$|\d+$)", re.IGNORECASE)

# How many of a page's first lines may hold a running head. Same window the
# running-element stripper uses.
HEAD_REGION = 3

# Minimum similarity between normalised strings for an OCR-tolerant match.
MATCH_RATIO = 0.85


@dataclass(frozen=True)
class OutlineEntry:
    level: int
    title: str      # verbatim, as the catalogue states it
    page: int       # physical page, 1-based


def save_outline(entries: list[OutlineEntry], out_dir: str | Path) -> Path | None:
    """Write the sidecar next to the page JSONs. No entries, no file."""
    if not entries:
        return None
    path = Path(out_dir) / OUTLINE_FILENAME
    payload = [
        {"level": e.level, "title": e.title, "page": e.page} for e in entries
    ]
    path.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def load_outline(src_dir: str | Path) -> list[OutlineEntry]:
    path = Path(src_dir) / OUTLINE_FILENAME
    if not path.exists():
        return []
    return [
        OutlineEntry(level=e["level"], title=e["title"], page=e["page"])
        for e in json.loads(path.read_text(encoding="utf-8"))
    ]


def credible(entries: list[OutlineEntry]) -> bool:
    """Document-wide junk filter, adapted from Archilles.

    Fewer than three entries carry no structure worth acting on; every entry
    pointing at one page or half the titles being scanner artifacts marks a
    mechanically generated outline.
    """
    if len(entries) < 3:
        return False
    if len({e.page for e in entries}) <= 1:
        return False
    junk = sum(1 for e in entries if _JUNK_TITLE_RE.match(e.title.strip()))
    return junk <= len(entries) * 0.5


def _norm(s: str) -> str:
    """Letters and digits only, case-folded: OCR spacing ("o f"), punctuation
    and line breaks fall away before comparing."""
    return "".join(c for c in s.lower() if c.isalnum())


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= MATCH_RATIO


def match_prefix_lines(lines: list[str], title: str) -> int | None:
    """How many leading lines of the page spell out ``title``, or None.

    A chapter opening prints the number and the title as separate lines
    ("2" / "The Surrender of Narbonne" / "to the Franks in 759"); accumulate
    lines until they cover the title, tolerating OCR noise.
    """
    want = _norm(title)
    if not want:
        return None
    got = ""
    for k, line in enumerate(lines[: HEAD_REGION + 2], start=1):
        got += _norm(line)
        if len(got) >= len(want) * MATCH_RATIO and _similar(got, want):
            return k
        if len(got) > len(want) * 1.2:
            return None
    return None


def chapter_headings(
    entries: list[OutlineEntry], pages_lines: list[list[str]]
) -> dict[int, tuple[str, int]]:
    """Verified level-1 chapter starts: {physical page: (title, leading lines)}.

    An entry acts only where its page actually shows the title. An entry the
    page does not confirm is dropped silently — a heading is an insertion into
    the text, and inserting on the catalogue's word alone would let a wrong
    outline rewrite the book.
    """
    headings: dict[int, tuple[str, int]] = {}
    for e in entries:
        if e.level != 1 or not (1 <= e.page <= len(pages_lines)):
            continue
        title = " ".join(e.title.split())
        k = match_prefix_lines(pages_lines[e.page - 1], title)
        if k is not None:
            headings[e.page] = (title, k)
    return headings


_LEAD_NUM = re.compile(r"^(\d{1,4})\s+")
_TRAIL_NUM = re.compile(r"\s+(\d{1,4})$")


def _strip_edges(s: str) -> tuple[str | None, str, str | None]:
    """Split off a leading and a trailing number: (lead, core, trail)."""
    s = s.strip()
    lead = trail = None
    m = _LEAD_NUM.match(s)
    if m:
        lead, s = m.group(1), s[m.end():]
    m = _TRAIL_NUM.search(s)
    if m:
        trail, s = m.group(1), s[: m.start()]
    return lead, s, trail


def strip_running_titles(
    pages_lines: list[list[str]], titles: list[str]
) -> list[list[str]]:
    """Remove chapter running heads from the head region of every page.

    Unlike the generic stripper this one knows the full title, so an edge
    number is kept only when it is *not* the title's own: the trailing year of
    "The Surrender … in 759" vanishes with the head instead of being preserved
    as a phantom folio, while a genuine folio sharing the line ("44 The
    Surrender …") survives for label detection.
    """
    # Each title, split at its numeric edges: chapter number, core, year.
    wants = []
    for t in titles:
        lead, core, trail = _strip_edges(" ".join(t.split()))
        if _norm(core):
            wants.append((lead, _norm(core), trail))
    if not wants:
        return pages_lines

    out: list[list[str]] = []
    for lines in pages_lines:
        kept: list[str] = []
        for i, line in enumerate(lines):
            if i >= HEAD_REGION:
                kept.extend(lines[i:])
                break
            lead, core, trail = _strip_edges(line)
            got = _norm(core)
            hit = next((w for w in wants if _similar(got, w[1])), None)
            if hit is None:
                kept.append(line)
                continue
            # The head goes; a folio that is not the title's own number stays.
            if lead is not None and lead != hit[0]:
                kept.append(lead)
            if trail is not None and trail != hit[2]:
                kept.append(trail)
        out.append(kept)
    return out
