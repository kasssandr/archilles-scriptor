"""Printed lines, assembled from the line fragments a backend reports.

A ``Line`` is what the backend saw, not what the typesetter set. Google Books splits
one printed line into several fragments; LuraDocument hands over one fragment per
word. Measured on five sample pages each: Seeck reports 731 lines where 216 are
printed, Origenes 363 for 183, Thil-Lorrain 162 for 130. Only Berliner and Josephus
arrive whole.

Downstream, ``calibrate_threshold`` builds its histogram from line lengths and
``is_prose_page`` measures the dominant width against them. Fed fragments of length
5, 26, 5 and 6, both produce plausible-looking, wrong paragraphs -- and say nothing
about it. Reassembling the printed line is therefore the first thing geometry buys.

**The baseline is the anchor, not the box.** Within one printed line of Seeck p.120
the box top scatters by 2.2 points -- ``'falls'`` at 92.97 against ``'sich'`` at
90.77, because ``falls`` has no ascender -- while the baseline scatters by 0.36.
Clustering on the box tears Seeck into 50 lines where 37 are printed, and leaves
Josephus entirely unclustered (43 for 34).

Columns are not resolved here. Joining across a column gap would be a judgement
about reading order that this module has no basis for. It counts the lines with a
suspiciously wide gap so the caller can say so out loud.
"""

from __future__ import annotations

from dataclasses import dataclass

from scriptor.page import Line, SourcePage
from scriptor.reflow.columns import Gutter, reading_order

# Points. Fragments of one printed line scatter by ~0.4pt on the baseline. Two
# points is already too generous: on the baseline it merges two real lines of Seeck
# (35 clusters where 37 are printed).
BASELINE_TOLERANCE = 1.0

# A horizontal gap this wide, relative to the page, is more likely a column boundary
# than a word space. The topmost and bottommost printed lines are exempt: a running
# head and its folio gape 84pt at 332pt page width in Zuckerman -- 25.3 % -- and
# that is not a column break.
WIDE_GAP_FRACTION = 0.33


@dataclass
class Reconstruction:
    lines: list[str]
    measured: bool          # True: assembled from baselines. False: passed through.
    wide_gap_lines: int     # printed lines holding a suspiciously wide gap
    sizes: list[float | None] = None    # dominant size per printed line, parallel to ``lines``
    indents: list[float | None] = None  # left edge (x0) per printed line, parallel to ``lines``
    # Characters at the head of the line the typesetter set apart (bold or
    # italic). A run-in heading is exactly that: "3.2.1 Lexical Search (Grep)."
    # in italics, the prose of the same printed line in roman.
    emphases: list[int] = None

    def __post_init__(self) -> None:
        if self.sizes is None:
            self.sizes = [None] * len(self.lines)
        if self.indents is None:
            self.indents = [None] * len(self.lines)
        if self.emphases is None:
            self.emphases = [0] * len(self.lines)


def _passthrough(page: SourcePage) -> Reconstruction:
    return Reconstruction(
        lines=[line.text for line in page.lines],
        measured=False,
        wide_gap_lines=0,
        sizes=[line.size for line in page.lines],
        indents=[line.box.x0 if line.box else None for line in page.lines],
    )


def _cluster_size(cluster: list[Line]) -> float | None:
    """The dominant size of a printed line, weighted by character count.

    Same rule as ``Line.size``, applied across the fragments of one cluster: a
    short bold run must not drag the whole line to its size. Ties go to the
    larger size, so the result does not depend on iteration order.
    """
    weights: dict[float, int] = {}
    for line in cluster:
        for span in line.spans:
            if span.size is None:
                continue
            weights[span.size] = weights.get(span.size, 0) + len(span.text)
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _emphasis_run(cluster: list[Line]) -> int:
    """Characters at the head of the printed line set in bold or italic.

    Counted over the cluster in reading order and stopped at the first roman
    span, because what matters is the *head* of the line: an italic work title
    in the middle of a sentence says nothing about the line's role.
    """
    run = 0
    for i, line in enumerate(cluster):
        if i:
            # The space assembly puts between two fragments belongs to the run,
            # or a heading handed over as "2.3" + "Tool-Calling Architectures"
            # would be cut one character short of its own last letter.
            run += 1
        for span in line.spans:
            if not (span.bold or span.italic):
                return run
            run += len(span.text)
    return run


# Characters a line needs before its box shape means anything. A single glyph is
# taller than it is wide in most faces, and says nothing about its direction.
SIDEWAYS_MIN_CHARS = 4

# How much taller than wide. Merely taller is not enough: Zuckerman p.399 carries
# an OCR scrap, "•־־׳־ 399", in a box 24pt wide and 30pt tall, and treating that
# as a stamp lifts it into the text the label detection had been dropping it from.
# A stamp runs down the margin — arXiv's is thirteen times taller than it is wide.
SIDEWAYS_RATIO = 3.0


def _sideways(line: Line) -> bool:
    """Is this line set across the page rather than along it?

    Measured, not declared: the backend reports no direction, but 40 characters
    in a box 27pt wide and 353pt tall can only be running down the margin.
    """
    if line.box is None or len(line.text.strip()) < SIDEWAYS_MIN_CHARS:
        return False
    width = line.box.x1 - line.box.x0
    return width > 0 and (line.box.y1 - line.box.y0) / width >= SIDEWAYS_RATIO


def _has_wide_gap(cluster: list[Line], threshold: float) -> bool:
    return any(
        b.box.x0 - a.box.x1 > threshold for a, b in zip(cluster, cluster[1:])
    )


def _cluster(lines: list[Line], tolerance: float) -> list[list[Line]]:
    """The printed lines of one block, in reading order."""
    ordered = sorted(lines, key=lambda line: (line.baseline, line.box.x0))

    clusters: list[list[Line]] = []
    for line in ordered:
        if clusters and line.baseline - clusters[-1][0].baseline <= tolerance:
            clusters[-1].append(line)
        else:
            clusters.append([line])

    for cluster in clusters:
        cluster.sort(key=lambda line: line.box.x0)
    return clusters


def reconstruct(
    page: SourcePage,
    *,
    tolerance: float = BASELINE_TOLERANCE,
    gutter: Gutter | None = None,
) -> Reconstruction:
    """Group the fragments of ``page`` into printed lines.

    With a ``gutter`` the page is cut into column blocks first and each block is
    clustered on its own, because two columns share one baseline grid: clustering
    across the lane would join the left column's line to the right column's.
    """
    if not page.lines:
        return _passthrough(page)
    if any(line.baseline is None or line.box is None for line in page.lines):
        # A half-measured page stays untouched: sorting the lines that do carry a
        # baseline would move the ones that do not to an arbitrary place.
        return _passthrough(page)

    # Lines set across the page — arXiv's margin stamp, a rotated plate caption —
    # carry a baseline that puts them in the middle of a paragraph. They are read
    # ahead of the page instead of inside it; deleting them would lose what they
    # say. Ahead, not after, because the foot of the page is where the printed
    # page number sits, and that number is the citation: a stamp behind it takes
    # the last line the label detection looks at.
    upright = [ln for ln in page.lines if not _sideways(ln)]
    sideways = [ln for ln in page.lines if _sideways(ln)]
    page = SourcePage(
        index=page.index, lines=upright, width=page.width, height=page.height,
        source=page.source, label=page.label,
    )

    blocks = reading_order(page, gutter) if gutter is not None else [page.lines]
    if sideways:
        blocks = [[ln] for ln in sideways] + blocks
    clusters = [cluster for block in blocks for cluster in _cluster(block, tolerance)]

    threshold = (page.width or 0.0) * WIDE_GAP_FRACTION
    inner = clusters[1:-1] if len(clusters) > 2 else []
    wide_gap_lines = (
        sum(1 for cluster in inner if _has_wide_gap(cluster, threshold))
        if threshold
        else 0
    )

    # Cells sit on a grid the page holds over several rows; that grid only exists
    # while the fragments still carry their boxes, so tables are folded here.
    from scriptor.reflow.tables import fold_tables

    rows = [[(line.box.x0, line.text) for line in cluster] for cluster in clusters]
    lines, sizes, indents, emphases = fold_tables(
        rows,
        [" ".join(line.text for line in cluster) for cluster in clusters],
        [_cluster_size(cluster) for cluster in clusters],
        [cluster[0].box.x0 for cluster in clusters],
        [_emphasis_run(cluster) for cluster in clusters],
    )

    return Reconstruction(
        lines=lines,
        measured=True,
        wide_gap_lines=wide_gap_lines,
        sizes=sizes,
        indents=indents,
        emphases=emphases,
    )


@dataclass(frozen=True)
class EdgeLine:
    """The outermost printed line of a page, with the place it holds.

    The folio is the one thing on a page whose *position* is the evidence. A
    volume prints it at the same height on every page, and that height is what
    lets a wider reading be risked on lines the narrow one refuses -- "XII" is a
    page number at the top of a Themistios page and a division number anywhere
    else in the book.

    ``height`` is the baseline as a fraction of the page height, because
    absolute points say nothing across volumes: an A4 reprint and an octavo put
    their folios in the same place and at different coordinates.
    """

    edge: str            # "top" | "bottom"
    text: str
    height: float        # baseline / page height; 0.0 at the top of the page
    x0: float
    x1: float
    size: float | None


def edge_lines(page: SourcePage, *, tolerance: float = BASELINE_TOLERANCE
               ) -> list[EdgeLine]:
    """The topmost and bottommost printed line of ``page``.

    Assembled the same way the body is (fragments clustered on the baseline), or
    "XVIII" and "INTRODUZIONE" arrive as two lines and the folio is legible in
    neither. Lines set across the page are left out: a margin stamp carries a
    baseline that would make it the top of the page.

    Empty where nothing was measured -- the bare TXT path has no geometry, and a
    witness that reasons about place has nothing to say there.
    """
    if not page.height:
        return []
    measured = [ln for ln in page.lines
                if ln.baseline is not None and ln.box is not None
                and ln.text.strip() and not _sideways(ln)]
    if not measured:
        return []

    clusters = sorted(_cluster(measured, tolerance),
                      key=lambda c: c[0].baseline)

    def edge_of(cluster, edge: str) -> EdgeLine:
        ordered = sorted(cluster, key=lambda ln: ln.box.x0)
        return EdgeLine(
            edge=edge,
            text=" ".join(ln.text for ln in ordered).strip(),
            height=cluster[0].baseline / page.height,
            x0=min(ln.box.x0 for ln in ordered),
            x1=max(ln.box.x1 for ln in ordered),
            size=_cluster_size(cluster),
        )

    if len(clusters) == 1:
        # One line is one witness. Which edge it belongs to is decided by where
        # it sits: a page holding nothing but its folio is a real case (a blank
        # verso between chapters), and calling that line both edges would let a
        # single page appear to speak twice.
        only = clusters[0]
        edge = "top" if only[0].baseline / page.height < 0.5 else "bottom"
        return [edge_of(only, edge)]
    return [edge_of(clusters[0], "top"), edge_of(clusters[-1], "bottom")]


def _text_under(page: SourcePage, box: Box) -> str:
    """The text whose spans sit inside ``box``, in reading order.

    By the middle of each span, not by overlap: a link rectangle is drawn snugly
    around what it makes clickable, and a span that merely grazes its edge
    belongs to the neighbour.
    """
    parts: list[tuple[float, str]] = []
    for line in page.lines:
        for span in line.spans:
            if span.box is None:
                continue
            cx = (span.box.x0 + span.box.x1) / 2
            cy = (span.box.y0 + span.box.y1) / 2
            if box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1:
                parts.append((span.box.x0, span.text))
    return " ".join(text for _x, text in sorted(parts)).strip()


def linked_lines(page: SourcePage) -> list[tuple[int, str]]:
    """``(target, reference)`` for the page reference of each linked line.

    A contents entry is linked in pieces. Josephus and Jesus makes each entry
    three links pointing at the same page -- the chapter number at the left
    margin, the title beside it, the printed page at the right (x = 367 of a
    442pt page). Libros makes the whole entry one link, number included. Both
    are answered by the same rule: **per printed line, the rightmost link is the
    page reference**, and what its own rectangle covers is what it says.

    That rule is what keeps the chapter number out. "1." is a link too, points
    at the same page, and reads as a bare numeral -- taking it would have every
    chapter opening claim to be page 1. It is never the rightmost.
    """
    if not page.links:
        return []
    measured = [ln for ln in page.lines
                if ln.baseline is not None and ln.box is not None]
    if not measured:
        return []

    # The baseline is the anchor, not the box -- the same rule the assembly
    # above follows, and here it is what keeps a single tall box from swallowing
    # the page. Josephus and Jesus has a cluster whose box union runs from y=185
    # to y=478 of a 660pt page; matching links by box overlap gave that one row
    # 28 of the page's 55 links and lost every contents entry behind it.
    baselines = [cluster[0].baseline
                 for cluster in _cluster(measured, BASELINE_TOLERANCE)]

    # A link rectangle is drawn around the text it makes clickable, so that
    # text's baseline lies inside it. Where several do -- a generous rectangle
    # reaching into the neighbouring line -- the nearest to the middle wins.
    per_row: dict[int, list] = {}
    for link in page.links:
        middle = (link.box.y0 + link.box.y1) / 2
        inside = [(abs(b - middle), i) for i, b in enumerate(baselines)
                  if link.box.y0 <= b <= link.box.y1]
        if inside:
            per_row.setdefault(min(inside)[1], []).append(link)

    out: list[tuple[int, str]] = []
    for i in sorted(per_row):
        rightmost = max(per_row[i], key=lambda l: (l.box.x1, l.box.x0))
        text = _text_under(page, rightmost.box)
        if text:
            out.append((rightmost.target, text))
    return out


# A first-line paragraph indent, relative to the page's stable left edge. The
# edge itself scatters by ~0.3pt (OCR boxes), so the band starts well above
# that; a centred heading or a deep quotation sits far beyond it and is not a
# paragraph start. Zuckerman indents by ~8.8pt.
INDENT_MIN = 4.0
INDENT_MAX = 18.0
# Lines that must sit on the modal edge before it counts as stable.
EDGE_MIN_LINES = 5


def mark_indent_breaks(
    lines: list[str], indents: list[float | None]
) -> list[str]:
    """Insert a blank line before each line that starts with a paragraph indent.

    The blank line is the same signal ``parse_page``/merge already read as a
    paragraph end, so the geometry flows through the existing seam. Only added
    when the page has a stable left edge, the offset falls inside the indent
    band, and the previous line does not end in a line-break hyphen — a
    continuation of a hyphenated word can never start a paragraph.
    """
    if len(lines) != len(indents):
        return lines
    edge_counts: dict[int, int] = {}
    for x in indents:
        if x is not None:
            edge_counts[round(x)] = edge_counts.get(round(x), 0) + 1
    if not edge_counts:
        return lines
    edge, count = max(edge_counts.items(), key=lambda kv: (kv[1], -kv[0]))
    if count < EDGE_MIN_LINES:
        return lines

    out: list[str] = []
    for i, (line, x) in enumerate(zip(lines, indents)):
        if (
            x is not None
            and INDENT_MIN <= x - edge <= INDENT_MAX
            and not (i > 0 and lines[i - 1].rstrip().endswith("-"))
        ):
            out.append("")
        out.append(line)
    return out
