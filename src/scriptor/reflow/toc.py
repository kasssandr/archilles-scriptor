"""TOC-Erkennung, -Erhaltung und seiten-basierte Verlinkung.

Importiert ``core`` auf Modulebene; ``core`` importiert dieses Modul nur lokal
in den Funktionen (Projektkonvention, vermeidet Zyklus).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scriptor.reflow.core import Page, render_frontmatter

TOC_LINK_THRESHOLD = 0.7

# Zeile endet auf eine plausible Seitenzahl (1-4 Ziffern).
_LINE_ENDS_NUM = re.compile(r"\d{1,4}\s*$")

# Saubere Eintragszeile: Titel + (Leader/Whitespace) + abschliessende Zahl.
_ENTRY_RE = re.compile(r"^(?P<title>.*?\S)[\s.]*\s(?P<page>\d{1,4})$")

# Fuehrende Gliederungsnummer: 1 / 1.1 / 1.1.2 …
_NUM_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(?P<rest>.*)$")


@dataclass
class TocEntry:
    title: str
    page: int          # gedruckte Seitenzahl laut TOC; -1 wenn keine
    level: int         # 1-basiert; 1 = oberste Ebene


@dataclass
class TocParse:
    entries: list[TocEntry]
    confidence: float


@dataclass
class TocRender:
    blocks: list[str]
    anchor_targets: set[int] = field(default_factory=set)


def is_toc_page(
    page: Page,
    *,
    min_entry_lines: int = 4,
    page_end_fraction: float = 0.6,
) -> bool:
    """True, wenn ein hinreichender Anteil der nicht-leeren Zeilen auf eine
    Seitenzahl endet (strukturelle, heading-lose TOC-Heuristik)."""
    lines = [ln.strip() for ln in page.body_lines if ln.strip()]
    if len(lines) < min_entry_lines:
        return False
    ending = sum(1 for ln in lines if _LINE_ENDS_NUM.search(ln))
    return ending >= min_entry_lines and ending / len(lines) >= page_end_fraction


def _split_numbering(title: str) -> tuple[int, str]:
    """(level, titel_ohne_nummer). Unnummeriert -> (1, titel)."""
    m = _NUM_PREFIX.match(title)
    if m:
        return m.group(1).count(".") + 1, m.group("rest").strip()
    return 1, title


def parse_toc(pages: list[Page]) -> TocParse:
    entries: list[TocEntry] = []
    non_empty = 0
    clean = 0
    for p in pages:
        for ln in p.body_lines:
            s = ln.strip()
            if not s:
                continue
            non_empty += 1
            m = _ENTRY_RE.match(s)
            if not m or not m.group("title").strip():
                continue
            level, title = _split_numbering(m.group("title").strip(" ."))
            if not title:
                continue
            entries.append(TocEntry(title=title, page=int(m.group("page")), level=level))
            clean += 1

    confidence = clean / non_empty if non_empty else 0.0
    seq = [e.page for e in entries if e.page >= 0]
    if len(seq) >= 2:
        non_decr = sum(1 for a, b in zip(seq, seq[1:]) if b >= a)
        mono = non_decr / (len(seq) - 1)
        confidence *= 0.5 + 0.5 * mono
    return TocParse(entries=entries, confidence=confidence)
