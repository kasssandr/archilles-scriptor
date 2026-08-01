from scriptor.page import Box, Line, SourcePage, Span
from scriptor.reflow.columns import Gutter, find_gutter
from scriptor.reflow.textlines import reconstruct


def _frag(text, x0, baseline, *, x1=None, top=None):
    """A line fragment. ``top`` defaults just above the baseline."""
    x1 = x1 if x1 is not None else x0 + 6 * len(text)
    top = top if top is not None else baseline - 7.0
    box = Box(x0, top, x1, baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=9.0)], box=box, baseline=baseline)


def _two_column_page(index, *, width=612.0, rows=20):
    """An ACM-style page: left column 55–296, right column 320–557."""
    lines = []
    for i in range(rows):
        y = 90.0 + i * 12.0
        lines.append(_frag(f"left line {i}", 55.0, y, x1=296.0))
        lines.append(_frag(f"right line {i}", 320.0, y, x1=557.0))
    return SourcePage(index=index, width=width, height=792.0, lines=lines)


def _single_column_page(index, *, width=332.0, rows=20):
    """Zuckerman: a running head, its folio, and full-measure prose."""
    lines = [
        _frag("The First Generations of the Jewish Principate", 30.0, 25.0, x1=225.0),
        _frag("193", 309.0, 25.0, x1=325.0),
    ]
    for i in range(rows):
        y = 60.0 + i * 12.5
        lines.append(_frag(f"prose line {i}", 30.0, y, x1=302.0))
    return SourcePage(index=index, width=width, height=792.0, lines=lines)


def test_a_two_column_document_reports_its_gutter():
    """Sen et al., 'Is Grep All You Need?': ACM sigconf, gutter 296–320 at 612pt."""
    pages = [_two_column_page(i) for i in range(1, 6)]

    gutter = find_gutter(pages)

    assert gutter is not None
    assert gutter.x0 == 296.0
    assert gutter.x1 == 320.0


def test_a_running_head_and_its_folio_are_not_a_gutter():
    """Zuckerman p.193: 84pt of white between title and folio, and nothing else
    up there. The prose below covers that band, so the document is single-column."""
    pages = [_single_column_page(i) for i in range(1, 6)]

    assert find_gutter(pages) is None


def test_a_wide_margin_beside_the_type_area_is_not_a_gutter():
    """Cell, 'Voices' format (603pt wide): the type area starts at 220 and the
    margin left of it carries a section label and the author's name and affiliation.

    Measured on the real file: 260 lines, a clear lane at 99--220pt. It is real,
    wide and still not a column boundary, because a column has to carry the text.
    Relax the two guards and the same pages do report that lane as a gutter.
    """
    pages = []
    for index in range(1, 6):
        lines = [
            _frag(f"margin note {i}", 53.0, 100.0 + i * 12.0, x1=99.0) for i in range(6)
        ]
        for i in range(30):
            lines.append(_frag(f"prose line {i}", 220.5, 120.0 + i * 12.0, x1=543.0))
        pages.append(SourcePage(index=index, width=603.0, height=792.0, lines=lines))

    assert find_gutter(pages) is None
    assert find_gutter(pages, min_side_share=0.0, min_depth=1) is not None


def test_two_fragments_of_one_printed_line_are_not_two_columns():
    """Thil-Lorrain: a printed line arrives in fragments, with white between them.

    The white is a word space that the backend happened to break on. A column is
    not a hole in one line, it is a hole many lines deep.
    """
    page = SourcePage(
        index=1, width=300.0, height=400.0,
        lines=[_frag("Die Fragmente einer Zeile", 30.0, 50.0),
               _frag("gehoeren zusammen.", 190.0, 50.4)],
    )

    assert find_gutter([page]) is None


def test_the_left_column_is_read_out_before_the_right():
    page = _two_column_page(1, rows=3)

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines == [
        "left line 0", "left line 1", "left line 2",
        "right line 0", "right line 1", "right line 2",
    ]


def test_without_a_gutter_the_two_columns_still_interleave():
    """The failure this module exists to fix, kept visible: same page, no gutter."""
    page = _two_column_page(1, rows=2)

    assert reconstruct(page).lines == [
        "left line 0 right line 0",
        "left line 1 right line 1",
    ]


def test_a_folio_centred_in_the_gutter_keeps_its_place():
    """ACM sets the page number centred on the measure, which puts it inside the
    lane. It belongs to neither column: assigned to one, it lands mid-page and the
    footer detection never sees it at the foot of the page again.
    """
    page = SourcePage(
        index=1,
        width=612.0,
        height=792.0,
        lines=[
            _frag("left column line", 55.0, 90.0, x1=296.0),
            _frag("right column line", 320.0, 90.0, x1=557.0),
            _frag("7", 303.0, 720.0, x1=309.0),
        ],
    )

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines == ["left column line", "right column line", "7"]


def test_a_float_does_not_cut_the_column_running_past_it():
    """Sen et al. p.5: Table 1 sits across the measure and the text flows past it.

    On paper the table interrupts both columns; in the sentence it interrupts
    nothing. So the left column is read whole, then the right, and the table
    after them — where it can no longer cut "…operates under very" from
    "different framing across harnesses".
    """
    page = SourcePage(
        index=5,
        width=612.0,
        height=792.0,
        lines=[
            _frag("above left", 55.0, 90.0, x1=296.0),
            _frag("above right", 320.0, 90.0, x1=557.0),
            _frag("Table 1: Overall accuracy on the 116-question subset", 55.0, 120.0,
                  x1=557.0),
            _frag("below left", 55.0, 150.0, x1=296.0),
            _frag("below right", 320.0, 150.0, x1=557.0),
        ],
    )

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines == [
        "above left",
        "below left",
        "above right",
        "below right",
        "Table 1: Overall accuracy on the 116-question subset",
    ]


def test_a_running_head_over_one_column_belongs_to_the_page():
    """Sen et al. prints "Sen et al." at x=525 on every page — right of the lane.

    Read as a line of the right column it lands between the two columns, in the
    middle of the running text, and the running-element stripper never sees it at
    the head of the page. Alone on the topmost baseline, it belongs to the page.
    """
    lines = [_frag("Sen et al.", 525.0, 60.0, x1=558.0)]
    for i in range(12):
        y = 90.0 + i * 12.0
        lines.append(_frag(f"left line {i}", 55.0, y, x1=296.0))
        lines.append(_frag(f"right line {i}", 320.0, y, x1=557.0))
    lines.append(_frag("3", 303.0, 720.0, x1=309.0))
    page = SourcePage(index=2, width=612.0, height=792.0, lines=lines)

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines[0] == "Sen et al."
    assert result.lines[-1] == "3"
    assert result.lines[1] == "left line 0"


def test_a_table_between_the_columns_is_read_after_them():
    """Sen et al. p.5 sets Table 1 across the top and lets the text flow past it.

    Read in printed order, the table lands between "…operates under very" and
    "different framing across harnesses", cutting a sentence that runs across the
    page break. A float is an insertion: the running text of the page is read
    first, the float after it — still on its page, before the folio.
    """
    lines = []
    for i in range(12):
        y = 150.0 + i * 12.0
        lines.append(_frag(f"left line {i}", 55.0, y, x1=296.0))
        lines.append(_frag(f"right line {i}", 320.0, y, x1=557.0))
    lines.append(_frag("Table 1: Overall accuracy on the subset", 55.0, 90.0, x1=557.0))
    lines.append(_frag("Model Harness grep vector", 55.0, 105.0, x1=557.0))
    lines.append(_frag("5", 303.0, 720.0, x1=309.0))
    page = SourcePage(index=5, width=612.0, height=792.0, lines=lines)

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines[0] == "left line 0"
    assert result.lines[11] == "left line 11"
    assert result.lines[12] == "right line 0"
    assert result.lines[24] == "Table 1: Overall accuracy on the subset"
    assert result.lines[-1] == "5"


def test_a_float_is_anchored_at_the_first_paragraph_break():
    """A float belongs to a seam in the text, not to the edge of the page: it
    goes where the page's first paragraph ends, at the indent that opens the
    second. Sen et al. p.5 opens with the tail of a sentence carried over from
    p.4 — Table 1 follows that, not the whole page.
    """
    lines = [
        _frag("carried over from the previous page and ending here.", 55.0, 150.0,
              x1=296.0),
        _frag("Der zweite Absatz beginnt eingerueckt und laeuft", 64.0, 162.0, x1=296.0),
        _frag("ueber mehrere Zeilen bis zum Ende der Spalte hier.", 55.0, 174.0, x1=296.0),
        _frag("right column line one", 320.0, 150.0, x1=557.0),
        _frag("Table 1: Overall accuracy on the subset", 55.0, 90.0, x1=557.0),
        _frag("5", 303.0, 720.0, x1=309.0),
    ]
    page = SourcePage(index=5, width=612.0, height=792.0, lines=lines)

    result = reconstruct(page, gutter=Gutter(296.0, 320.0))

    assert result.lines == [
        "carried over from the previous page and ending here.",
        "Table 1: Overall accuracy on the subset",
        "Der zweite Absatz beginnt eingerueckt und laeuft",
        "ueber mehrere Zeilen bis zum Ende der Spalte hier.",
        "right column line one",
        "5",
    ]
