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

from collections import Counter
from dataclasses import dataclass

from scriptor.reflow.outline import OutlineEntry, match_prefix_lines



@dataclass(frozen=True)
class ChapterStart:
    pos: int        # positional page index, 1-based, as Page.index counts
    title: str      # as the catalogue states it, whitespace normalised
    rank: int       # outline level, 1 = coarsest; verbatim, not renumbered
    source: str     # "outline" | "toc"


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


def principal_rank(starts: list[ChapterStart]) -> int | None:
    """The level this volume opens its chapters on, or None.

    The level carrying the most confirmed openings; on a tie the coarser one,
    because that is the level that means "chapter". Volumes differ in where
    they put their chapters and the answer has to come from the volume rather
    than from a convention: Artificial Humanities opens them on level 1,
    Asclepios on level 2.

    Taking the *coarsest* level with a couple of openings looks more cautious
    and is worse. Asclepios confirms two entries on level 1 -- "Cover" and
    "Inhoudsopgave", which the pages do spell out -- against nineteen chapters
    on level 2, and the cautious rule would hand the recto witness the front
    matter and none of the chapters.
    """
    per_rank = Counter(c.rank for c in starts)
    if not per_rank:
        return None
    return min(per_rank, key=lambda r: (-per_rank[r], r))
