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
from typing import Iterable

from scriptor.reflow.heads import HeadCandidates, without_edge_number
from scriptor.reflow.rescued import RescuedFolios

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


def fold(s: str) -> str:
    """Letters and digits only, case-folded: OCR spacing ("o f"), punctuation
    and line breaks fall away before comparing.

    The one folding every title comparison in this repository uses; the
    heading metric folds the same way (``scriptor.eval.headings``)."""
    return "".join(c for c in s.lower() if c.isalnum())


def similar(a: str, b: str) -> bool:
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
    want = fold(title)
    if not want:
        return None
    got = ""
    for k, line in enumerate(lines[: HEAD_REGION + 2], start=1):
        got += fold(line)
        if len(got) >= len(want) * MATCH_RATIO and similar(got, want):
            return k
        if len(got) > len(want) * 1.2:
            return None
    return None


def title_line_spans(lines: list[str], title: str) -> list[tuple[int, int]]:
    """Every run of lines that spells ``title`` out: (first line, how many).

    ``match_prefix_lines`` asks the same question of the page's first lines
    only, because it is used to *cut* those lines off. A contents search cuts
    nothing, and the page it is looking for does not always open with the
    title: a section heading stands where the previous section ended, which is
    anywhere down the page. De eerste minister sets "De geschiedenis van de
    raadpensionaris" on line 7 of the page that opens it -- and on line 1 of
    the page after, as a running head. Reading only the head therefore finds
    the furniture and misses the heading, which is the wrong way round.

    Accumulates from each start in turn, with the same tolerance and the same
    length bound, so a title still has to be spelt out by whole lines and a
    long paragraph can never drift into a match. Every run is reported, not
    just the first: the placement rule needs to know that the wording stands
    on the page a second time, in the head region, where a running head goes
    (Gliederungsmodell §5.2, rule 6).

    How many lines a run takes is the other half of the answer. A title the
    printer broke across two lines owns both of them, and a word of the page
    never belongs half to a heading (§5.2, rule 8).
    """
    return folded_spans([fold(line) for line in lines], fold(title))


def folded_spans(lines: list[str], want: str, *,
                 opens: bool = False) -> list[tuple[int, int]]:
    """``title_line_spans`` on lines and a title already folded.

    The placement asks this of every title against every page, and folding a
    page anew for each of them was the whole cost of the search.

    ``opens`` demands that the first line of a run *begin* the title. Without
    it a run may start one line early wherever that line is short enough for
    the rest to still look similar: "Phänomene." over "A. Bildliche Aneignung
    – eine Definition" matched as one, and a caller that cuts where the run
    begins then cuts a word of the paragraph into the heading. A caller that
    only asks *whether* a page spells the title out is not affected by this
    and keeps the older, looser reading.
    """
    spans: list[tuple[int, int]] = []
    if not want:
        return spans
    for start in range(len(lines)):
        if opens:
            head = lines[start]
            if not head or not similar(head, want[: len(head)]):
                continue
        got = ""
        for k, line in enumerate(lines[start: start + HEAD_REGION + 2], start=1):
            got += line
            if len(got) >= len(want) * MATCH_RATIO and similar(got, want):
                spans.append((start, k))
                break
            if len(got) > len(want) * 1.2:
                break
    return spans


def match_title_lines(lines: list[str], title: str) -> int | None:
    """The first line from which ``lines`` spell ``title`` out, or None."""
    spans = title_line_spans(lines, title)
    return spans[0][0] if spans else None


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

# Below this many folded characters a title recognises too much: "I.", "A.",
# a bare numeral. Five is where Bauer's "4. Fazit" sits, a wording it prints
# over three different sections and which the generic stripper deleted from
# every one of them.
MIN_KNOWN_TITLE = 5


class KnownTitles:
    """The titles a volume's own lists name, to be recognised on a page.

    The contents and the outline together. What either of them calls a
    heading is a title this volume prints, and a head-region line carrying one
    is either that heading or the running head repeating it (§5.5a) -- in both
    cases something the generic stripper must not decide about on its own.

    Folded and compared the way every other title match in this module is,
    with the numeric edges of the line taken off first: a running head prints
    "23 B. Gang der Darstellung", and the folio is not part of the title.
    """

    __slots__ = ("_by_fold",)

    def __init__(self, titles: Iterable[str]) -> None:
        self._by_fold: dict[str, str] = {}
        for title in titles:
            whole = " ".join(title.split())
            key = fold(_strip_edges(whole)[1])
            if len(key) >= MIN_KNOWN_TITLE:
                self._by_fold.setdefault(key, whole)

    def of(self, line: str) -> str | None:
        """The known title this line carries, or None."""
        key = fold(_strip_edges(line)[1])
        if len(key) < MIN_KNOWN_TITLE:
            return None
        hit = self._by_fold.get(key)
        if hit is not None:
            return hit
        # Length rules a pair out before difflib walks it -- ``similar`` is
        # by far the most expensive thing here, and a volume asks it of every
        # head line against every title it knows.
        lo, hi = len(key) * MATCH_RATIO, len(key) / MATCH_RATIO
        return next((title for known, title in self._by_fold.items()
                     if lo <= len(known) <= hi and similar(key, known)), None)

    def __len__(self) -> int:
        return len(self._by_fold)


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
    pages_lines: list[list[str]], titles: list[str], rescued: RescuedFolios,
    heads: HeadCandidates | None = None,
    lists: frozenset[int] | set[int] = frozenset(),
) -> tuple[list[list[str]], int]:
    """Remove chapter running heads from the head region of every page.

    Unlike the generic stripper this one knows the full title, so an edge
    number is rescued only when it is *not* the title's own: the trailing year
    of "The Surrender … in 759" vanishes with the head instead of being taken
    for a folio, while a genuine folio sharing the line ("44 The Surrender …")
    is handed on for the consensus to weigh.

    Returns (cleaned_pages, contested); the folios go to ``rescued`` at the top
    edge, and ``contested`` counts how many *lines* offered two. One line can carry a
    number at both edges and only one of them can be the folio; there the
    leading one wins, because that is the edge a volume printing its folio in
    the running head uses when the title also ends in a number. Across lines
    nothing is chosen: a page can carry two heads, and two heads are two
    statements. The count is reported rather than swallowed: it is the size of
    the case nobody has measured yet.

    With a ``heads`` channel the line is not removed but recorded and left
    standing, its rescued folio taken off it (``reflow.heads``): every title
    this stripper knows is a title the outline names, so every line it would
    delete is one the placement rule has to judge. Without the channel it
    deletes as before — the callers that have no placement stage, and the
    tests that measure this stripper alone.
    """
    # Each title, split at its numeric edges: chapter number, core, year.
    wants = []
    for t in titles:
        whole = " ".join(t.split())
        lead, core, trail = _strip_edges(whole)
        if fold(core):
            wants.append((lead, fold(core), trail, whole))
    if not wants:
        return pages_lines, 0

    out: list[list[str]] = []
    contested = 0
    for index, lines in enumerate(pages_lines):
        kept: list[str] = []
        for i, line in enumerate(lines):
            if i >= HEAD_REGION:
                kept.extend(lines[i:])
                break
            lead, core, trail = _strip_edges(line)
            got = fold(core)
            hit = next((w for w in wants if similar(got, w[1])), None)
            if hit is None:
                kept.append(line)
                continue
            # The head goes; a folio that is not the title's own number is
            # rescued -- as a statement, not as a line put back into the text.
            folios = [n for n, own in ((lead, hit[0]), (trail, hit[2]))
                      if n is not None and n != own]
            if len(folios) > 1:
                contested += 1
            if folios:
                rescued.add(index, "top", folios[0])
            if heads is not None:
                # On a contents page the line stays whole: the number at its
                # edge is the entry's page, not this page's folio.
                stays = (line if index in lists else
                         without_edge_number(line, folios[0] if folios else None))
                heads.add(index, len(kept), stays, hit[3])
                kept.append(stays)
        out.append(kept)
    return out, contested
