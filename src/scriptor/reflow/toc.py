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
