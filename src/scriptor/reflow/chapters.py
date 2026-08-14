"""Where a volume's chapters begin.

The pagination plan needs this: a printed count jumps where a chapter opens,
because that is where the printer suppresses a blank or starts a new sheet. The
recto witness needs it too, for the rule that a chapter opens on an odd page.
Neither can ask the outline directly -- the outline states pages the *catalogue*
believes in, and it is right about them often enough to be useful and wrong
often enough to be dangerous. What is taken here is confirmed on the page.

Two things this module keeps apart, because its two customers need different
things from the same finding:

*Position.* Every confirmed start is a place where the count may jump. A
subsection start is a worse guess than a chapter start and still a better one
than nothing, so the plan gets them all.

*Rank.* "A chapter opens on an odd page" is a claim about the top of a book's
structure. A subsection beginning halfway down a page says nothing about it, so
the recto witness asks ``principal_rank`` for the level this volume actually
opens its chapters on, and looks at those alone.

Finding a start is not the same as writing a heading into the text. Headings
stay where they are (``outline.chapter_headings``, level 1 only): a heading is
an insertion into the author's text and carries a risk this module does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scriptor.reflow.outline import OutlineEntry, match_prefix_lines

# A title that numbers itself below a top level: "II.1", "2.3.1.", "1.1.". The
# entry says what it is and no count can overrule it -- a volume may well carry
# more subsections than chapters, which is where counting alone goes wrong.
# Measured: Asclepios numbers 10 entries on level 3 and 3 on level 4 this way,
# Libros 21 and 5, A comemoração 5.
_SUBSECTION = re.compile(r"^\s*(?:[IVXLCivxlc]+|\d{1,3})\s*\.\s*\d")

# What the binder wrapped around the book. These are not parts of a book's
# division, so a level made of nothing else is the level on which the finished
# object was assembled -- not the level on which it is organised. Measured on
# level 1: "Cover" and "Half Title" (Oxford Handbook), "Cubierta" and "Portada"
# (Libros), "Cover" (Asclepios, Libros, bauer-aneignung, De eerste minister),
# and at mehr-themistios the bare ISBN, twice. The rest are the immediate
# neighbours of those in the corpus languages.
_PACKAGING = re.compile(
    r"^(?:"
    r"front\s*cover|back\s*cover|cover|half[-\s]*title|title\s*page|"
    r"umschlag|schutzumschlag|titelblatt|titelei|impressum|kolophon|"
    r"omslag|voorplat|achterplat|titelpagina|colofon|"
    r"cubierta|portada|portadilla|colof[óo]n|cr[ée]ditos|"
    r"copertina|frontespizio|colophon|couverture|page\s*de\s*titre|"
    r"capa|folha\s*de\s*rosto|ficha\s*t[ée]cnica"
    r")$|^\d[\d\s-]{6,}$",   # ... and a bare ISBN is not a title at all
    re.IGNORECASE,
)



# What a contents line puts in front of a title and the chapter page does not:
# ornaments and a numbering the page may set differently. Carlomagno lists
# "• La humanidad de Carlos" and prints it without the bullet.
_ORNAMENT = re.compile(r"^[\s•▪◦‣*]+|^\s*(?:[IVXLC]+|\d{1,3})[.)]?\s+")

# A contents line often trails dots to its page number. What survives the
# parser can still carry them, and they are not part of the title.
_LEADER = re.compile(r"[\s.]{3,}$")

# Below this a "title" is not one: an initial, a stray numeral, a leader dash.
MIN_TOC_TITLE = 4


@dataclass(frozen=True)
class ChapterStart:
    pos: int        # positional page index, 1-based, as Page.index counts
    title: str      # as the catalogue states it, whitespace normalised
    rank: int       # outline level, 1 = coarsest; verbatim, not renumbered
    source: str     # "outline" | "toc"
    # What the table of contents says this page is called in print. A statement
    # about a *label*, which is why it travels: the outline has no such thing,
    # and a chapter opening is exactly where a volume tends to print no folio.
    printed: str | None = None


def from_outline(
    entries: list[OutlineEntry], pages_lines: list[list[str]]
) -> list[ChapterStart]:
    """The outline entries whose page actually shows their title.

    Every level is asked. The old restriction to level 1 was never argued for
    and costs most of the evidence: over the eleven corpus volumes with an
    outline it confirms 31 starts where asking every level confirms 112.
    Publishers put "Cover", "Inhoudsopgave" or the volume's ISBN on level 1 and
    the chapters one level down -- at Asclepios level 1 yields 2 starts and
    level 2 yields 19, at mehr-themistios level 1 yields none and level 2 all
    thirteen.

    The confirmation rule is untouched: the page has to spell out the title.
    """
    best: dict[int, ChapterStart] = {}
    for e in entries:
        if not (1 <= e.page <= len(pages_lines)):
            continue
        title = " ".join(e.title.split())
        if match_prefix_lines(pages_lines[e.page - 1], title) is None:
            continue
        # A chapter and its first subsection open on the same page often enough
        # to matter. As a position that is one place, and the coarser rank is
        # the true one -- the page is where a chapter begins, whatever else
        # begins there with it.
        found = best.get(e.page)
        if found is None or e.level < found.rank:
            best[e.page] = ChapterStart(
                pos=e.page, title=title, rank=e.level, source="outline"
            )
    return [best[p] for p in sorted(best)]


def from_toc(
    entries, lines_by_pos: dict[int, list[str]], toc_positions: set[int]
) -> list[ChapterStart]:
    """Contents entries placed by their title, carrying their printed page.

    The number in a contents line is a *printed* page, and turning that into a
    position needs the plan this is meant to inform. The title needs nothing:
    it is searched across the volume, and the page that spells it out is the
    position. What the entry claims about the printed page then travels along
    as ``printed`` -- evidence about a label rather than an address.

    ``toc_positions`` are the pages of the contents itself, and they are not a
    place to look: every title stands there. Measured at Carlomagno, two of
    four apparent hits were the contents page listing them.
    """
    out: dict[int, ChapterStart] = {}
    for e in entries:
        title = _LEADER.sub("", _ORNAMENT.sub("", e.title)).strip()
        if len(title) < MIN_TOC_TITLE:
            continue
        head = title.split()[0].lower()
        for pos, lines in sorted(lines_by_pos.items()):
            if pos in toc_positions or pos in out:
                continue
            # A cheap gate before the expensive comparison: a page that opens a
            # chapter prints the title's first word in its first lines.
            if head not in " ".join(lines[:4]).lower():
                continue
            if match_prefix_lines(lines, title) is None:
                continue
            out[pos] = ChapterStart(
                pos=pos, title=title, rank=e.level, source="toc",
                printed=str(e.page) if e.page >= 0 else None,
            )
            break
    return _in_reading_order([out[p] for p in sorted(out)])


def _in_reading_order(starts: list[ChapterStart]) -> list[ChapterStart]:
    """Drop the finds that break the order a contents list is written in.

    A contents lists in reading order, so read down the volume its printed
    pages rise. The trap this catches is the volume's own title: it stands in
    the contents *and* on the title page, and a title search finds it there. At
    De eerste minister that produced "position 2 is printed page 250", which
    cost the volume its front-matter segment and three markers.

    Checking the offset instead would be wrong. Carlomagno's offset grows from
    0 to 5 across the book -- its PDF drops the blank before every chapter
    opening -- and all thirteen of its finds are right. Order survives that;
    a constant offset does not.

    Kept: the longest rising run of printed pages, ties to the earlier finds.
    A find with no printed page states nothing about order and always stays.
    """
    numbered = [(i, c) for i, c in enumerate(starts) if c.printed is not None]
    if len(numbered) < 2:
        return starts
    values = [int(c.printed) for _i, c in numbered
              if c.printed and c.printed.isdigit()]
    if len(values) != len(numbered):        # roman or unreadable: leave it be
        return starts
    # Longest non-decreasing subsequence, by position.
    best: list[int] = []           # length -> index of its last element
    prev = [-1] * len(values)
    for k, v in enumerate(values):
        lo, hi = 0, len(best)
        while lo < hi:
            mid = (lo + hi) // 2
            if values[best[mid]] <= v:
                lo = mid + 1
            else:
                hi = mid
        prev[k] = best[lo - 1] if lo else -1
        if lo == len(best):
            best.append(k)
        else:
            best[lo] = k
    keep: set[int] = set()
    k = best[-1] if best else -1
    while k >= 0:
        keep.add(numbered[k][0])
        k = prev[k]
    return [c for i, c in enumerate(starts)
            if c.printed is None or i in keep]


def _is_subsection_level(titles: list[str]) -> bool:
    """Most of these entries number themselves below a top level."""
    hits = sum(1 for t in titles if _SUBSECTION.match(t))
    return hits * 2 > len(titles)


def _is_packaging_level(titles: list[str]) -> bool:
    """Nothing here is a part of the book -- only what was wrapped around it."""
    return bool(titles) and all(_PACKAGING.match(t.strip()) for t in titles)


def principal_rank(starts: list[ChapterStart]) -> int | None:
    """The level this volume opens its chapters on, or None.

    Asked in two steps, and the order is the point. First the titles are read:
    a level whose entries number themselves as subsections ("II.1") is not a
    chapter level whatever it counts, and neither is one made of nothing but
    packaging ("Cover", "Half Title", a bare ISBN). Both are properties of the
    entries themselves, so no distribution of the corpus can flip them.

    Only then does the count decide, among the levels the titles did not rule
    out: most openings wins, ties to the coarser level. That last step is a
    heuristic and is meant to look like one -- it is there because at Asclepios
    the titles genuinely do not settle the question. Level 1 there carries
    "Inhoudsopgave" and "Verantwoording van de afbeeldingen": parts of a book,
    not packaging, not numbered. What separates them from the nineteen chapters
    on level 2 is that level 2 divides the whole volume while level 1 divides it
    into the three parcels the finished object was assembled from -- a fact
    about how many and how spread, not about what they are called.

    Where every level is ruled out, the count decides alone: the question still
    has to be answered, and a volume of nothing but subsections is numbered by
    its subsections.
    """
    per_rank: dict[int, list[str]] = {}
    for c in starts:
        per_rank.setdefault(c.rank, []).append(c.title)
    if not per_rank:
        return None
    eligible = [
        r for r, titles in per_rank.items()
        if not _is_subsection_level(titles) and not _is_packaging_level(titles)
    ] or list(per_rank)
    return min(eligible, key=lambda r: (-len(per_rank[r]), r))
