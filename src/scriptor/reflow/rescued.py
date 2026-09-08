"""Folios lifted out of lines a stripper removed.

Four stages reach into a line they are about to delete and keep the number that
shared it — the generic head and foot strippers, the one that knows the chapter
titles, and the one that cleans a footnote block the geometry cut off. The
number is not put back into the text: the line was furniture, and a bare number
in its place is indistinguishable from a folio the page prints in its own right
(``pagination/witnesses.rescued_observations``).

What they hand back used to be four parallel lists that ``reflow.core`` stitched
together again. This is the one channel instead: each stage *adds* to it, and
nothing between them has to be kept in step. It is the smallest form of the
direction ``reflow/__init__`` describes — a record the stages mark rather than
replace — and the place to look when a fifth rescue path appears.
"""

from __future__ import annotations


class RescuedFolios:
    """Per page, the numbers rescued from removed furniture, by edge.

    Positions are 1-based physical pages, as everything downstream of
    ``reflow.core`` counts them. A page may carry several: two running heads say
    different things (Josephus and Jesus heads its pages with a download banner
    ending in the year *and* with the chapter's running head ending in the
    folio), and both edges may speak. The same number stated twice at one edge
    is one statement and is dropped.
    """

    __slots__ = ("_at",)

    def __init__(self, pages: int) -> None:
        self._at: list[list[tuple[str, str]]] = [[] for _ in range(pages)]

    def add(self, index: int, edge: str, label: str | None) -> None:
        """Record ``label`` at the given edge of the page at ``index`` (0-based).

        A ``None`` label is the ordinary case — most removed lines carry no
        number — and is ignored rather than refused.
        """
        if label is None:
            return
        if edge not in ("top", "bottom"):
            raise ValueError(f"an edge is top or bottom, not {edge!r}")
        here = self._at[index]
        if (edge, label) not in here:
            here.append((edge, label))

    def by_position(self) -> dict[int, list[tuple[str, str]]]:
        """What the consensus reads: {physical page: [(edge, label), …]}.

        Only pages that carry something. Ordered top before bottom, in the order
        the stages added them, so the witnesses reach the fit in a fixed order
        whatever the pages did.
        """
        return {
            i: sorted(rescues, key=lambda r: (r[0] != "top",))
            for i, rescues in enumerate(self._at, start=1)
            if rescues
        }

    def at(self, index: int) -> list[tuple[str, str]]:
        """What page ``index`` (0-based) carries. Used where a stage has to know
        whether a page it just emptied held anything at all."""
        return self._at[index]

    def __len__(self) -> int:
        return sum(1 for rescues in self._at if rescues)
