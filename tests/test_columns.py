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


def test_a_line_crossing_the_gutter_separates_the_bands():
    """Sen et al. p.5: Table 1 runs the full measure between two blocks of prose.

    Read down the left column, across the table, and only then into the right —
    the table belongs where the page put it, not before or after both columns.
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
        "above right",
        "Table 1: Overall accuracy on the 116-question subset",
        "below left",
        "below right",
    ]
