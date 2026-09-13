"""Head-region lines that carry a title the volume itself names.

A running head and the heading it repeats print the same words, and on the
page that opens the section they are the same line. The generic stripper
cannot tell them apart: it sees a wording repeated three times and deletes
every copy, the heading among them (Gliederungsmodell §2.7).

So the strippers stop deciding. A head-region line whose words are a title
the contents or the outline names is left standing and recorded here;
``reflow.placement`` judges it once the page labels are known, and what it
does not confirm is removed then. Deferring instead of deleting is the
direction the evidence order asks for, and this channel has the shape
``RescuedFolios`` has: one list per page, added to by more than one stage,
read once.

Where a stripper had judged such a line furniture of its own accord, the folio
it carries is rescued on the spot, exactly as before -- the consensus counts it
before the judgement runs -- and taken out of the line that stays, so that the
same number is not read twice. Where only the known title brought the line
here, nothing is rescued and nothing is taken off it: the line was not going to
be deleted at all, and the pagination must hear what it heard before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEAD_NUM = re.compile(r"^(\d{1,4})\s+")
_TRAIL_NUM = re.compile(r"\s+(\d{1,4})$")


def without_edge_number(line: str, number: str | None) -> str:
    """The line without the folio that shared it and has just been rescued.

    Only that one number, and only where it still stands at the edge: what a
    stripper read out of the line is what comes off it, so the two can never
    drift apart. A line that carried none comes back as it was.
    """
    s = line.strip()
    if not number:
        return s
    m = _LEAD_NUM.match(s)
    if m and m.group(1) == number:
        return s[m.end():]
    m = _TRAIL_NUM.search(s)
    if m and m.group(1) == number:
        return s[: m.start()]
    return s


@dataclass(frozen=True)
class HeadCandidate:
    """A head-region line a stripper would have deleted, and where it stood."""

    page_index: int     # 0-based, as the strippers count pages
    line_index: int     # where it stands in the page the stripper handed on
    text: str           # the line as it stays in the text, without its folio
    title: str          # the known title it carries, as the list states it
    # Whether a stripper would have deleted this line of its own accord. It
    # decides what happens to a candidate the placement does not confirm: one
    # the stripper had already judged furniture goes, as it went before; one
    # that only the known title brought here goes only where that same title
    # was placed somewhere else, because rule 6 speaks of every *further*
    # occurrence, and without a first one there is nothing to be further than.
    from_stripper: bool = True


class HeadCandidates:
    """Per page, the head-region lines left standing for the placement to judge.

    Positions are 0-based, as the strippers count them; ``reflow.core`` turns
    them into the 1-based physical pages everything downstream uses.
    """

    __slots__ = ("_at",)

    def __init__(self, pages: int) -> None:
        self._at: list[list[HeadCandidate]] = [[] for _ in range(pages)]

    def add(self, index: int, line_index: int, text: str, title: str,
            from_stripper: bool = True) -> None:
        self._at[index].append(
            HeadCandidate(index, line_index, text, title, from_stripper))

    def at(self, index: int) -> list[HeadCandidate]:
        """What page ``index`` (0-based) carries."""
        return self._at[index]

    def by_position(self) -> dict[int, list[HeadCandidate]]:
        """{physical page (1-based): [candidate, …]}, only pages that carry one."""
        return {i: cands for i, cands in enumerate(self._at, start=1) if cands}

    def __len__(self) -> int:
        return sum(len(cands) for cands in self._at)
