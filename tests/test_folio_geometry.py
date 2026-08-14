"""The second round: what a page says at the edge the volume paginates at.

The narrow reading has had its turn by the time any of this runs. What is left
are the pages it could not read, and the only thing that makes a second, wider
reading defensible is that the volume has already shown -- on hundreds of pages
-- where it puts its folio. So the tests here are about *place* first and text
second: the same string is a page number at one height and a line of the book at
another.
"""

from scriptor.page import Box, Line, SourcePage, Span
from scriptor.reflow.textlines import edge_lines


def _line(text, y, x0=100.0, size=9.0):
    return Line(
        spans=[Span(text, box=Box(x0, y - 8, x0 + 40, y), size=size)],
        box=Box(x0, y - 8, x0 + 40, y),
        baseline=y,
    )


def _page(*lines, height=800.0):
    return SourcePage(index=1, lines=list(lines), width=600.0, height=height)


def test_the_edges_are_the_outermost_printed_lines():
    page = _page(_line("XII", 40), _line("Text der Seite.", 300),
                 _line("312", 760))
    got = {(e.edge, e.text) for e in edge_lines(page)}
    assert ("top", "XII") in got
    assert ("bottom", "312") in got


def test_an_edge_line_knows_its_height_as_a_fraction():
    # Absolute points say nothing across volumes -- A4 and octavo put their
    # folios at the same place and at different coordinates.
    page = _page(_line("XII", 40), _line("Text.", 300), height=800.0)
    top = next(e for e in edge_lines(page) if e.edge == "top")
    assert top.height == 0.05


def test_the_edge_is_read_off_the_baseline_not_the_list_order():
    # lines[0] is the extraction order. Sorting by it has spoiled a diagnosis
    # before (design §4.2), so the geometry decides here.
    page = _page(_line("312", 760), _line("Text.", 300), _line("XII", 40))
    top = next(e for e in edge_lines(page) if e.edge == "top")
    assert top.text == "XII"


def test_the_fragments_of_one_printed_line_arrive_as_one_edge():
    # "XVIII" at x=90 and "INTRODUZIONE" at x=140 are one printed line of Gli
    # Actus, and the folio is only legible when they are read together.
    page = _page(_line("XVIII", 40, x0=90), _line("INTRODUZIONE", 40, x0=140),
                 _line("Text.", 300))
    top = next(e for e in edge_lines(page) if e.edge == "top")
    assert top.text == "XVIII INTRODUZIONE"


def test_a_page_without_geometry_has_no_edges():
    # The bare TXT path measures nothing, and a witness that reasons about
    # place has nothing to say there.
    page = SourcePage(index=1, lines=[Line(spans=[Span("42")])])
    assert edge_lines(page) == []


def test_a_page_without_a_height_has_no_edges():
    page = _page(_line("42", 760), height=None)
    assert edge_lines(page) == []


def test_a_single_line_page_is_one_edge_not_two():
    # Otherwise the same line would be offered as both witnesses and a page
    # would appear to speak twice.
    page = _page(_line("42", 400))
    assert len(edge_lines(page)) == 1


# ----------------------------------------------------------------------
# The band: where this volume prints its folios, learnt from what was confirmed
# ----------------------------------------------------------------------

from scriptor.reflow.pagination.witnesses import (   # noqa: E402
    folio_band,
    geometric_observations,
)
from scriptor.reflow.textlines import EdgeLine       # noqa: E402


def _edge(edge, text, height, x0=100.0, size=9.0):
    return EdgeLine(edge=edge, text=text, height=height, x0=x0, x1=x0 + 40,
                    size=size)


def test_the_band_is_learnt_from_where_the_confirmed_folios_stood():
    band = folio_band([("bottom", 0.95), ("bottom", 0.951), ("bottom", 0.949),
                       ("bottom", 0.95), ("bottom", 0.952)])
    assert band.edge == "bottom"
    assert band.lo <= 0.949 and band.hi >= 0.952


def test_the_band_belongs_to_the_edge_that_carried_the_folios():
    # Both edges get looked at, and one of them is where the volume paginates.
    # Gli Actus confirmed 340 labels at the top and 8 at the foot -- the eight
    # are last lines of prose that happened to end in a number, and a band
    # learnt from them would open the body text to a wider reading.
    sightings = [("top", 0.104)] * 6 + [("bottom", 0.72), ("bottom", 0.73)]
    band = folio_band(sightings)
    assert band.edge == "top"


def test_a_volume_that_showed_no_habit_gets_no_band():
    # Four confirmations are not a habit. Nothing is learnt, and the second
    # reading does not happen at all -- silence, not a guess.
    assert folio_band([("bottom", 0.95)] * 4) is None
    assert folio_band([]) is None


def test_the_witness_reads_what_the_narrow_detector_refused():
    band = folio_band([("bottom", 0.95)] * 6)
    obs = geometric_observations({7: [_edge("bottom", "XII", 0.951)]}, band)
    assert [(o.pos, o.label, o.weight) for o in obs] == [(7, "XII", 0.8)]
    assert obs[0].source == "printed-geometric"


def test_the_witness_stays_out_of_the_body():
    # The same string, twelve points further up, is a line of the book. This is
    # the whole difference between the second reading and simply lowering the
    # bar.
    band = folio_band([("bottom", 0.95)] * 6)
    obs = geometric_observations({7: [_edge("bottom", "XII", 0.80)]}, band)
    assert obs == []


def test_the_witness_asks_only_the_edge_the_volume_paginates_at():
    band = folio_band([("bottom", 0.95)] * 6)
    obs = geometric_observations({7: [_edge("top", "XII", 0.05)]}, band)
    assert obs == []


def test_the_witness_is_silent_where_the_page_already_spoke():
    # A page that printed a folio the narrow reading could read has said its
    # piece. Asking again could only produce a second, weaker voice arguing
    # with the first.
    band = folio_band([("bottom", 0.95)] * 6)
    edges = {7: [_edge("bottom", "XII", 0.951)]}
    assert geometric_observations(edges, band, spoken_for={7}) == []


def test_the_witness_carries_its_reason():
    band = folio_band([("bottom", 0.95)] * 6)
    obs = geometric_observations({7: [_edge("bottom", ". 50.", 0.95)]}, band)
    assert obs[0].label == "50"
    assert "foot" in obs[0].why and "50" in obs[0].why


def test_without_a_band_the_second_reading_does_not_happen():
    assert geometric_observations({7: [_edge("bottom", "XII", 0.95)]}, None) == []


# ----------------------------------------------------------------------
# The verdict, with both rounds: La masonería in miniature
# ----------------------------------------------------------------------

from scriptor.reflow.core import Page                      # noqa: E402
from scriptor.reflow.pagination.verdict import run_verdict  # noqa: E402


def _volume():
    """Six arabic pages the narrow reading can take, four versal ones it cannot.

    This is La masonería's shape: a versal front matter the volume paginates at
    the foot, then an arabic body at the same foot. Today the front matter comes
    out uncounted and 64 printed, counted pages lose their labels.
    """
    pages, edges = [], {}
    for i, label in enumerate(["XI", "XII", "XIII", "XIV"], start=1):
        pages.append(Page(num=-1, body_lines=["Vorwort."], index=i))
        edges[i] = [_edge("bottom", label, 0.95)]
    for i, label in enumerate(["1", "2", "3", "4", "5", "6"], start=5):
        pages.append(Page(num=-1, body_lines=["Text."], index=i,
                          label_bottom=label))
        edges[i] = [_edge("bottom", label, 0.95)]
    return pages, edges


def test_the_versal_front_matter_gets_its_labels():
    pages, edges = _volume()
    run_verdict(pages, edges=edges)
    assert [p.label for p in pages[:4]] == ["XI", "XII", "XIII", "XIV"]


def test_a_geometric_reading_counts_as_printed():
    # The page did print it -- only the narrow reading could not take it. The
    # difference to a label the first round read is carried by the confidence,
    # not by the source: archilles reads label_source to know whether a page
    # stated its own number, and this one did.
    pages, edges = _volume()
    run_verdict(pages, edges=edges)
    assert [p.label_source for p in pages[:4]] == ["printed"] * 4
    assert all(p.label_confidence and p.label_confidence < 1.0 for p in pages[:4])


def test_the_arabic_body_is_untouched_by_the_second_round():
    pages, edges = _volume()
    run_verdict(pages, edges=edges)
    assert [p.label for p in pages[4:]] == ["1", "2", "3", "4", "5", "6"]


def test_the_two_numbering_systems_stay_two_segments():
    pages, edges = _volume()
    verdict = run_verdict(pages, edges=edges)
    styles = [s.style for s in verdict.plan.segments if s.kind == "counted"]
    assert styles == ["roman-upper", "arabic"]


def test_without_geometry_the_verdict_is_what_it_was():
    # The TXT path measures nothing. Etappe 1's behaviour has to survive that
    # unchanged, or the second round is not an addition but a replacement.
    pages, _edges = _volume()
    run_verdict(pages)
    assert [p.label for p in pages[:4]] == [None] * 4
    assert [p.label for p in pages[4:]] == ["1", "2", "3", "4", "5", "6"]


def test_a_roman_gap_between_two_confirmed_pages_is_closed():
    # Etappe 1 wrote nothing back into a roman stretch, because an arabic label
    # is its own ordinal and roman needed an encoder that did not exist. The
    # unprinted page between XI and XIII is enclosed exactly as 13 is between 12
    # and 14 -- the reason for the restraint was the encoder, not the arithmetic.
    pages, edges = _volume()
    edges[2] = [_edge("bottom", "Vorwort", 0.95)]     # this page prints no folio
    run_verdict(pages, edges=edges)
    assert [p.label for p in pages[:4]] == ["XI", "XII", "XIII", "XIV"]
    assert pages[1].label_source == "computed"


def test_a_computed_roman_label_keeps_the_case_of_its_segment():
    # A volume setting "XI" is cited as "XI". Writing back "xi" would invent a
    # page the volume never printed -- the same mistake as re-encoding an
    # observed label.
    pages, edges = _volume()
    for i, label in enumerate(["xi", "xii", "xiii", "xiv"], start=1):
        edges[i] = [_edge("bottom", label, 0.95)]
    edges[2] = [_edge("bottom", "Vorwort", 0.95)]
    run_verdict(pages, edges=edges)
    assert [p.label for p in pages[:4]] == ["xi", "xii", "xiii", "xiv"]


def test_a_lone_geometric_reading_founds_nothing():
    # min_attested applies to the second round exactly as to the first: seven of
    # thirty segments once rested on a single reading and every one was wrong.
    pages, edges = _volume()
    edges[1] = [_edge("bottom", "XI", 0.95)]
    for i in (2, 3, 4):
        edges[i] = [_edge("bottom", "Vorwort", 0.95)]
    run_verdict(pages, edges=edges)
    assert pages[0].label is None
