"""The vertical lane between two set columns, and the reading order it implies.

``textlines`` assembles a printed line from the fragments that share a baseline.
In a two-column setting both columns sit on the same baseline grid, so that rule
joins the left column's line to the right column's and the prose comes out
interleaved word for word. Sen et al., *Is Grep All You Need?* (ACM sigconf, 612pt
wide, columns 55--296 and 320--557) reads ``Abstract with agent architecture and
tool-calling paradigm ... Recent advances in Large Language Model (LLM) agents
have enadoption of agentic search``: every word present, the argument destroyed.

The gutter is measured across the whole document, not per page. A page carrying a
full-width table has no lane of its own, and a book whose last page holds four
lines would report one that is not there. What makes a lane a gutter is that the
document keeps it clear.

Reading order is then a recursive cut: lines that cross the lane (a title, a
full-width table, an author block) separate the page into bands; inside a band the
left column is read before the right. Nothing here decides what a line *is* --
that stays in ``core`` (README: "A backend reports, it does not judge").
"""

from __future__ import annotations

from dataclasses import dataclass

from scriptor.page import Line, SourcePage

# Points. A lane narrower than this is the white between two words of a running
# head, not a column boundary; ACM sets 24pt, two-column lexica 10--20pt.
MIN_GUTTER_WIDTH = 8.0

# Lines that may cross the lane and it still counts as a gutter. Cross-column
# tables and titles are the reason this is not zero: page 5 of Sen et al. spends
# 39 of 151 lines on a full-width table, but the document as a whole spends 4 %.
MAX_CROSSING_SHARE = 0.10

# Each side must carry this share of the document's lines. Without it, a column of
# marginal numbers beside a wide type area would qualify as a second column.
MIN_SIDE_SHARE = 0.20

# Printed lines a column must be deep, on the page that shows it best. A column is
# not a hole in one line -- Thil-Lorrain hands over a printed line in four
# fragments, and the white between two of them is a word space, not a gutter.
MIN_COLUMN_DEPTH = 10

# Only the middle of the page is searched. Margins are white by definition, and a
# lane hard against the type area is a hanging indent, not a second column.
SEARCH_BAND = (0.25, 0.75)

# Points a line may reach into the lane and still belong to its column. A line
# ending 1pt inside the gutter is a long word in justified type, not a title.
LANE_TOLERANCE = 2.0

# Points within which two fragments count as sitting on one printed baseline, for
# the table check in ``reading_order``. Same order as ``textlines.BASELINE_TOLERANCE``.
BASELINE_GROUP = 1.0

# Share of its column a line must fill before it counts as running text rather
# than as part of a page's head matter. An author's name fills a third of it.
HEAD_WIDTH_SHARE = 0.6

# A first-line indent, relative to the column's own left edge. Same band as
# ``textlines.INDENT_MIN``/``INDENT_MAX``, read here to find the seam a float
# can be anchored at.
INDENT_MIN = 4.0
INDENT_MAX = 18.0


@dataclass(frozen=True)
class Gutter:
    """The clear vertical lane, in PDF points from the left page edge."""

    x0: float
    x1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0


def _boxed(pages: list[SourcePage]) -> list[Line]:
    return [
        line
        for page in pages
        for line in page.lines
        if line.box is not None and line.text.strip()
    ]


def _page_width(pages: list[SourcePage]) -> float | None:
    """The dominant page width. A single foldout must not move the search band."""
    counts: dict[float, int] = {}
    for page in pages:
        if page.width:
            counts[page.width] = counts.get(page.width, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _clear_zones(lines: list[Line], max_crossing: int) -> list[tuple[float, float]]:
    """Sweep the x axis and return the runs no more than ``max_crossing`` lines cover."""
    events: list[tuple[float, int]] = []
    for line in lines:
        events.append((line.box.x0, 1))
        events.append((line.box.x1, -1))
    events.sort()

    zones: list[tuple[float, float]] = []
    covering = 0
    start: float | None = None
    i = 0
    while i < len(events):
        x = events[i][0]
        while i < len(events) and events[i][0] == x:
            covering += events[i][1]
            i += 1
        # ``covering`` now holds what covers the interval that starts at x.
        if covering <= max_crossing:
            if start is None:
                start = x
        elif start is not None:
            zones.append((start, x))
            start = None
    # A zone still open past the last line is the right margin, not a gutter.
    return zones


def _column_depth(pages: list[SourcePage], x0: float, x1: float) -> tuple[int, int]:
    """Printed lines left and right of the lane, counted on the page that shows most.

    Baselines are rounded to the point: the fragments of one printed line scatter
    by ~0.4pt and must count once, while two printed lines sit ~12pt apart.
    """
    left = right = 0
    for page in pages:
        measured = [
            line
            for line in page.lines
            if line.box is not None and line.baseline is not None and line.text.strip()
        ]
        left = max(left, len({round(ln.baseline) for ln in measured if ln.box.x1 <= x0}))
        right = max(right, len({round(ln.baseline) for ln in measured if ln.box.x0 >= x1}))
    return left, right


def find_gutter(
    pages: list[SourcePage],
    *,
    min_width: float = MIN_GUTTER_WIDTH,
    max_crossing_share: float = MAX_CROSSING_SHARE,
    min_side_share: float = MIN_SIDE_SHARE,
    min_depth: int = MIN_COLUMN_DEPTH,
) -> Gutter | None:
    """The lane this document keeps clear between two columns, if it keeps one."""
    lines = _boxed(pages)
    width = _page_width(pages)
    if not lines or not width:
        return None

    lo, hi = SEARCH_BAND[0] * width, SEARCH_BAND[1] * width
    zones = [
        z
        for z in _clear_zones(lines, int(len(lines) * max_crossing_share))
        if z[1] - z[0] >= min_width and lo <= (z[0] + z[1]) / 2 <= hi
    ]
    if not zones:
        return None

    needed = len(lines) * min_side_share
    for x0, x1 in sorted(zones, key=lambda z: z[0] - z[1]):
        left = sum(1 for ln in lines if ln.box.x1 <= x0)
        right = sum(1 for ln in lines if ln.box.x0 >= x1)
        if left < needed or right < needed:
            continue
        deep_left, deep_right = _column_depth(pages, x0, x1)
        if deep_left >= min_depth and deep_right >= min_depth:
            return Gutter(x0, x1)
    return None


def _anchor_floats(
    column: list[Line], right: list[Line], floats: list[list[Line]]
) -> list[list[Line]]:
    """Place the page's floats at the seam its first paragraph ends on.

    A table set across the measure has to go *somewhere* in a linear text, and
    the foot of the page is the one place it certainly does not belong: layout
    decides where a float is printed, so it rarely stands where the argument
    first names it. The first paragraph break of the page is a real seam —
    reached at the first indented line, which is where the second paragraph
    starts. Without one (a page holding a single paragraph) the floats follow the
    column, as before.
    """
    tail = [right] if right else []
    if not floats:
        return ([column] if column else []) + tail
    if not column:
        return tail + floats

    edge = min(ln.box.x0 for ln in column)
    cut = next(
        (
            i
            for i, ln in enumerate(column)
            if i and INDENT_MIN <= ln.box.x0 - edge <= INDENT_MAX
        ),
        None,
    )
    if cut is None:
        # No seam on this page: the float follows the text, as it did before.
        return [column] + tail + floats
    return [column[:cut]] + floats + [column[cut:]] + tail


def _is_plain_columns(lines: list[Line], gutter: Gutter) -> bool:
    """Does this baseline hold at most one line per column, as prose does?"""
    seen: set[str] = set()
    for line in lines:
        side = column_of(line, gutter)
        if side in seen:
            return False
        if side is not None:
            seen.add(side)
    return True


def _spans_lane(line: Line, gutter: Gutter) -> bool:
    """Does the line reach past both edges of the lane — a title, a wide table?"""
    if line.box is None:
        return False
    return (
        gutter.x0 - line.box.x0 > LANE_TOLERANCE
        and line.box.x1 - gutter.x1 > LANE_TOLERANCE
    )


def column_of(line: Line, gutter: Gutter) -> str | None:
    """``"left"``, ``"right"``, or ``None`` for a line no column owns.

    Ownership is decided by clearing the lane, not by which half of the page the
    line sits in. A full-measure title crosses it; ACM's folio is centred *inside*
    it. Both belong to the page rather than to a column, and both have to stay at
    the height the page put them -- a folio moved into a column lands mid-page,
    where the footer detection will never see it again.
    """
    if line.box is None:
        return None
    left_of_lane = gutter.x0 - line.box.x0
    right_of_lane = line.box.x1 - gutter.x1
    if left_of_lane > LANE_TOLERANCE and right_of_lane > LANE_TOLERANCE:
        return None                             # crosses: a title, a wide table
    if left_of_lane <= LANE_TOLERANCE and right_of_lane <= LANE_TOLERANCE:
        return None                             # sits in the lane: the folio
    # Protruding into the lane from one side keeps the line with its column: the
    # lane's edge is where the *document* clears, and single lines reach past it.
    return "left" if left_of_lane > right_of_lane else "right"


def reading_order(page: SourcePage, gutter: Gutter) -> list[list[Line]]:
    """Split one page into blocks, in the order a reader takes them.

    A line the columns do not own closes the band above it and opens one of its
    own, so a full-width table between two blocks of prose is read where the page
    put it: left column, table, right column -- not left, right, table.
    """
    ordered = sorted(page.lines, key=lambda line: (line.baseline, line.box.x0))

    # A full-measure table is invisible cell by cell: "Model" sits left of the
    # lane and "89.3" right of it, so the rule below would tear every row in two.
    # Its grid gives it away, and its rows are read as bands.
    from scriptor.reflow.tables import spanning_rows

    groups: list[list[Line]] = []
    for line in ordered:
        if groups and abs(line.baseline - groups[-1][0].baseline) <= BASELINE_GROUP:
            groups[-1].append(line)
        else:
            groups.append([line])
    tabular = spanning_rows(
        [[(ln.box.x0, ln.text) for ln in group] for group in groups], gutter
    )
    in_table = {id(ln) for i in tabular for ln in groups[i]}

    # The topmost and bottommost baseline, when nothing shares it, belongs to the
    # page and not to a column: that is where the running head and the folio sit.
    # Sen et al. prints its head at x=525 on every page, right of the lane — read
    # as a line of the right column it lands between the two columns, in the
    # middle of the running text, where the running-element stripper (which looks
    # at the head of the page) can no longer see it.
    # …but only where that line stays on one side of the lane or inside it. A
    # line spanning the measure up there is a title or a table caption, and those
    # are floats, not furniture.
    page_furniture = {
        id(group[0])
        for group in (groups[0], groups[-1])
        if len(group) == 1 and len(groups) > 1 and not _spans_lane(group[0], gutter)
    }

    # The head of page one is set in its own measure — ACM puts five authors in
    # three columns there, which the two-column rule reads as prose and posts
    # into the running text ("…how retrieval strategy interacts Elias Lumer
    # PricewaterhouseCoopers, U.S."). It ends at the first baseline that is both
    # set in the document's two columns and filling one: a name is short, a line
    # of prose reaches the edge of its column.
    head_matter: set[int] = set()
    column_width = gutter.x0 - min(ln.box.x0 for ln in ordered)
    for group in groups:
        if _is_plain_columns(group, gutter) and any(
            ln.box.x1 - ln.box.x0 >= column_width * HEAD_WIDTH_SHARE for ln in group
        ):
            break
        head_matter.update(id(ln) for ln in group)

    # Furniture is taken out before the bands are built, or it would merge with
    # whatever follows it: on page 5 the running head and the caption of Table 1
    # sit on consecutive baselines, and a shared band would carry the caption to
    # the head of the page with it.
    head: list[list[Line]] = []
    foot: list[list[Line]] = []
    for line in ordered:
        if id(line) in page_furniture:
            (head if line is groups[0][0] else foot).append([line])
    ordered = [ln for ln in ordered if id(ln) not in page_furniture]

    bands: list[tuple[bool, list[Line]]] = []
    for line in ordered:
        columnar = (
            id(line) not in in_table
            and id(line) not in page_furniture
            and id(line) not in head_matter
            and column_of(line, gutter) is not None
        )
        if bands and bands[-1][0] == columnar:
            bands[-1][1].append(line)
        else:
            bands.append((columnar, [line]))

    # Furniture keeps its place, floats move behind the text. A table set across
    # the measure is an insertion, not a turn in the argument: read where the page
    # prints it, Sen's Table 1 lands between "…operates under very" and "different
    # framing across harnesses" and cuts a sentence that runs across the page
    # break. Read after the columns, the prose is whole and the table still sits
    # on its own page, ahead of the folio that closes it.
    floats: list[list[Line]] = []
    sides: dict[str, list[Line]] = {"left": [], "right": []}
    seen_column = False

    for columnar, lines in bands:
        if not columnar:
            if not seen_column and page.index <= 1:
                # Above the first line of columned text, on the page that opens
                # the document: the title block. Anywhere else a band up there is
                # a table or a figure the text flows past — a float.
                head.append(lines)
            else:
                floats.append(lines)
            continue
        seen_column = True
        # Collected per side across the whole page, not per band: a float
        # interrupts a column on paper but not in the sentence running through it.
        for line in lines:
            sides[column_of(line, gutter)].append(line)

    left, right = sides["left"], sides["right"]
    return head + _anchor_floats(left, right, floats) + foot
