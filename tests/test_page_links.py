"""Internal links: a measured fact about a page, like a box or a size.

A PDF link carries its target as a page reference the file itself resolves. On a
contents page that is the answer to the question the contents witness otherwise
has to reach by searching for a title in the text -- the producer stating where
the entry goes, rather than Scriptor inferring it.

Only links that point *inside* the document are kept. A URI says nothing about
this volume's pagination, and a link whose destination the file cannot resolve
is a name, not a reference (measured on the corpus: PyMuPDF returns the resolved
page for both GOTO and named destinations, but leaves an unresolvable name as a
string that is not a page).
"""

import json

from scriptor.page import Box, Line, Link, SourcePage, Span, dumps, loads


def _page(**kw):
    return SourcePage(index=1, lines=[Line(spans=[Span("Text")])], **kw)


def test_a_link_carries_where_it_sits_and_where_it_goes():
    link = Link(box=Box(10.0, 20.0, 100.0, 32.0), target=21)
    assert link.target == 21
    assert link.box.x0 == 10.0


def test_links_survive_the_json_round_trip():
    page = _page(links=[Link(box=Box(1.0, 2.0, 3.0, 4.0), target=21)])
    back = loads(dumps(page))
    assert [(l.target, l.box.x1) for l in back.links] == [(21, 3.0)]


def test_a_page_without_links_writes_no_key():
    # Absent measurements are omitted, never written as null: a missing key says
    # "nothing was measured here", which null would blur into "measured, and it
    # was nothing".
    assert "links" not in json.loads(dumps(_page()))


def test_a_page_model_without_links_still_loads():
    page = loads(dumps(_page()))
    assert page.links == []


# ── pairing a link with the line it covers ───────────────────────────

from scriptor.reflow.textlines import linked_lines      # noqa: E402


def _line(text, y, x0=20.0, x1=200.0):
    box = Box(x0, y - 9, x1, y + 2)
    return Line(spans=[Span(text, box=box)], box=box, baseline=y)


def test_a_link_is_paired_with_the_line_it_covers():
    page = SourcePage(
        index=1, width=300.0, height=400.0,
        lines=[_line("Kapitel 1 .......... 31", 100),
               _line("Kapitel 2 .......... 47", 120)],
        links=[Link(box=Box(20.0, 92.0, 200.0, 103.0), target=51)],
    )
    assert linked_lines(page) == [(51, "Kapitel 1 .......... 31")]


def test_the_line_with_the_largest_overlap_wins():
    # Link rectangles are drawn generously and often reach into the line above.
    page = SourcePage(
        index=1, width=300.0, height=400.0,
        lines=[_line("Kapitel 1 .......... 31", 100),
               _line("Kapitel 2 .......... 47", 112)],
        links=[Link(box=Box(20.0, 104.0, 200.0, 115.0), target=67)],
    )
    assert linked_lines(page) == [(67, "Kapitel 2 .......... 47")]


def test_a_link_over_nothing_is_dropped():
    page = SourcePage(
        index=1, width=300.0, height=400.0,
        lines=[_line("Kapitel 1 .......... 31", 100)],
        links=[Link(box=Box(20.0, 300.0, 200.0, 320.0), target=51)],
    )
    assert linked_lines(page) == []


def test_a_page_without_geometry_pairs_nothing():
    page = SourcePage(index=1, lines=[Line(spans=[Span("Kapitel 1 ... 31")])],
                      links=[Link(box=Box(0.0, 0.0, 9.0, 9.0), target=5)])
    assert linked_lines(page) == []
