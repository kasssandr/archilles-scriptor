"""The verdict: which label a page carries, from whom, and how sure.

These tests are the behavioural contract of the rebuild. Every case below is one
that ``tests/test_page_label_gaps.py`` already pins on the older chain -- if one
of them changes, the rebuild changed behaviour, and the change has to be argued
rather than absorbed.

The runs print two labels on either side of a gap rather than one. One would
state the arithmetic just as well, but a lone reading no longer establishes a
numbering system at all (``FitParams.min_attested``), so a one-label run would
be testing that rule instead of the one it is here to state.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.verdict import run_verdict


def _page(index, label=None):
    return Page(num=-1, body_lines=["Etwas Text."], index=index,
                label_bottom=label)


def _labels(pages):
    return [p.label for p in pages]


# ----------------------------------------------------------------------
# what may be written back, and what may not
# ----------------------------------------------------------------------

def test_an_enclosed_page_is_labelled():
    pages = [_page(1, "11"), _page(2, "12"), _page(3), _page(4, "14")]
    run_verdict(pages)
    assert _labels(pages) == ["11", "12", "13", "14"]


def test_a_run_of_unprinted_pages_is_filled():
    pages = [_page(1, "24"), _page(2), _page(3), _page(4), _page(5, "28")]
    run_verdict(pages)
    assert _labels(pages) == ["24", "25", "26", "27", "28"]


def test_an_uncounted_plate_leaves_the_gap_open():
    pages = [_page(1, "11"), _page(2, "12"), _page(3), _page(4),
             _page(5, "14"), _page(6, "15")]
    run_verdict(pages)
    assert _labels(pages) == ["11", "12", None, None, "14", "15"]


def test_a_double_page_scan_leaves_the_gap_open():
    pages = [_page(1, "11"), _page(2, "12"), _page(3), _page(4, "15"),
             _page(5, "16")]
    run_verdict(pages)
    assert _labels(pages) == ["11", "12", None, "15", "16"]


def test_a_gap_that_counts_backwards_is_left_alone():
    pages = [_page(1, "40"), _page(2, "41"), _page(3), _page(4, "12"),
             _page(5, "13")]
    run_verdict(pages)
    assert _labels(pages) == ["40", "41", None, "12", "13"]


def test_the_front_is_counted_backwards_to_page_one():
    # Bauer prints "7" on physical page 7; the six before it are title pages.
    pages = [_page(i) for i in range(1, 7)] + [_page(7, "7"), _page(8, "8")]
    run_verdict(pages)
    assert _labels(pages) == ["1", "2", "3", "4", "5", "6", "7", "8"]


def test_counting_backwards_stops_at_page_one():
    # Themistios prints "2" on physical page 17: exactly one page is reachable.
    pages = [_page(i) for i in range(14, 17)] + [_page(17, "2"), _page(18, "3")]
    run_verdict(pages)
    assert _labels(pages) == [None, None, "1", "2", "3"]


def test_the_tail_is_never_extrapolated():
    pages = [_page(1, "8"), _page(2, "9"), _page(3), _page(4)]
    run_verdict(pages)
    assert _labels(pages) == ["8", "9", None, None]


def test_a_roman_gap_stays_open_and_roman_labels_stay_roman():
    pages = [_page(1, "vii"), _page(2), _page(3, "ix")]
    run_verdict(pages)
    assert _labels(pages) == ["vii", None, "ix"]


def test_a_script_change_leaves_the_page_between_undecided():
    pages = [_page(1, "iii"), _page(2, "iv"), _page(3), _page(4, "3"),
             _page(5, "4")]
    run_verdict(pages)
    assert _labels(pages) == ["iii", "iv", None, "3", "4"]


def test_a_backwards_run_does_not_start_from_a_roman_label():
    pages = [_page(1), _page(2), _page(3, "vii"), _page(4, "viii")]
    run_verdict(pages)
    assert _labels(pages) == [None, None, "vii", "viii"]


def test_a_fully_printed_volume_is_untouched():
    pages = [_page(i, str(10 + i)) for i in range(1, 6)]
    run_verdict(pages)
    assert _labels(pages) == ["11", "12", "13", "14", "15"]


def test_a_volume_without_labels_says_so():
    pages = [_page(1), _page(2), _page(3)]
    verdict = run_verdict(pages)
    assert _labels(pages) == [None, None, None]
    assert verdict.description == "none"


def test_a_page_without_a_physical_index_keeps_only_what_it_printed():
    pages = [Page(num=-1, body_lines=["Text."], label_bottom=lbl)
             for lbl in ("12", None, "14")]
    run_verdict(pages)
    assert _labels(pages) == ["12", None, "14"]


# ----------------------------------------------------------------------
# where the label comes from, and how sure it is
# ----------------------------------------------------------------------

def test_the_source_of_every_label_is_recorded():
    pages = [_page(1), _page(2, "2"), _page(3), _page(4, "4")]
    run_verdict(pages)
    assert _labels(pages) == ["1", "2", "3", "4"]
    assert [p.label_source for p in pages] == [
        "computed", "printed", "computed", "printed",
    ]


def test_the_ordinal_is_set_alongside_the_label():
    pages = [_page(1, "12"), _page(2), _page(3, "14")]
    run_verdict(pages)
    assert [p.num for p in pages] == [12, 13, 14]


def test_an_unlabelled_page_keeps_the_ordinal_minus_one():
    pages = [_page(1, "8"), _page(2)]
    run_verdict(pages)
    assert pages[1].num == -1


def test_a_printed_label_is_more_confident_than_a_computed_one():
    labels = ["1", "2", "3", "4", "5", None, "7", "8", "9", "10"]
    pages = [_page(i, lbl) for i, lbl in enumerate(labels, start=1)]
    run_verdict(pages)
    assert pages[5].label == "6"
    assert pages[0].label_confidence > pages[5].label_confidence


def test_the_verdict_counts_what_it_computed():
    pages = [_page(1, "12"), _page(2), _page(3, "14")]
    assert run_verdict(pages).computed_count == 1


# ----------------------------------------------------------------------
# what the plan rejects
# ----------------------------------------------------------------------

def test_a_contradicted_observation_is_reported_not_dropped():
    # The "2020" of an imprint page: rejected as a label, kept as a finding.
    pages = [_page(1, "11"), _page(2, "2020"), _page(3, "13"), _page(4, "14")]
    verdict = run_verdict(pages)
    assert [o.label for o in verdict.rejected] == ["2020"]


def test_a_misread_page_gets_the_label_the_volume_implies():
    # The reading was wrong; the page is still enclosed, and 12 is the only
    # value it can hold. The older chain took "2020" at face value.
    pages = [_page(1, "11"), _page(2, "2020"), _page(3, "13"), _page(4, "14")]
    run_verdict(pages)
    assert pages[1].label == "12" and pages[1].label_source == "computed"


def test_the_losing_edge_is_not_a_finding():
    # A running head read as a folio on every page is the other edge, not a
    # discovery. Reporting it would bury the real findings.
    pages = [Page(num=-1, body_lines=["T."], index=i,
                  label_bottom=str(i), label_top="12") for i in range(1, 8)]
    verdict = run_verdict(pages)
    assert verdict.rejected == []


def test_counting_backwards_needs_the_floor_it_claims():
    # The front edge differs from the back edge only because of the floor at
    # page 1, so a run that does not reach the floor has no more standing than a
    # run off the back. Two readings, because with one the support rule would
    # decide the case before the floor was ever consulted.
    pages = [_page(1), _page(2), _page(3), _page(4, "1972"), _page(5, "1973")]
    run_verdict(pages)
    assert _labels(pages) == [None, None, None, "1972", "1973"]


def test_a_lone_year_on_an_imprint_page_founds_nothing():
    # L'Empire: a year on the imprint page, no folio on the pages either side.
    # Counting back from it gave the first three pages the labels 1968, 1969,
    # 1970. Two rules now stand in the way and the outer one answers first --
    # one reading is not a numbering system, so there is no run to count back.
    pages = [_page(1), _page(2), _page(3), _page(4, "1972"), _page(5)]
    run_verdict(pages)
    assert _labels(pages) == [None, None, None, None, None]


def test_an_arabic_run_does_not_reach_back_across_a_roman_front_matter():
    # La masonería paginates its front matter in roman up to LXII. An arabic run
    # counted back over it and relabelled the page printing "vii" as "148".
    pages = ([_page(i) for i in range(1, 9)] + [_page(9, "vii")]
             + [_page(i, str(i + 138)) for i in range(10, 20)])
    run_verdict(pages)
    assert pages[8].label != "148"
    assert all(p.label is None for p in pages[:8])


def test_a_segment_does_not_reach_past_what_it_attests():
    # Between its first and last confirmation a segment speaks for the pages in
    # between -- that is what lets it overrule a chapter number read as a folio.
    # Backwards past its own first page it speaks for nothing, so p2 stays blank
    # rather than being counted back to.
    #
    # p1 used to keep its "1972" here, on the grounds that where the plan attests
    # nothing the page's own reading stands. It no longer does: a reading nothing
    # else supports is not a numbering system (FitParams.min_attested), and over
    # the corpus every label that rule removes was a misreading of this kind.
    pages = [_page(1, "1972"), _page(2), _page(3, "1"), _page(4, "2"),
             _page(5, "3"), _page(6, "4")]
    run_verdict(pages)
    assert [p.label for p in pages] == [None, None, "1", "2", "3", "4"]


def test_inside_the_span_the_plan_wins():
    # The counterpart: a chapter number enclosed by the running count is
    # overruled, because there the plan does vouch for the page.
    pages = [_page(1, "45"), _page(2, "46"), _page(3, "2"), _page(4, "48")]
    run_verdict(pages)
    assert pages[2].label == "47"


def test_a_label_from_the_contents_says_so():
    """``label_source`` names the strongest witness that confirmed this page, and
    the contents is not the catalogue.

    Masones has no PDF catalogue at all and six of its pages were nonetheless
    recorded as "catalogue" -- their labels come from its table of contents. The
    field travels to archilles, which reads it to know how far to trust a
    citation, so it has to say what it means.
    """
    from scriptor.reflow.chapters import ChapterStart

    pages = [_page(i) for i in range(1, 8)]
    pages[3].body_lines = ["Rey de los Francos", "Text."]
    starts = [ChapterStart(pos=4, title="Rey de los Francos", rank=1,
                           source="toc", printed="4"),
              ChapterStart(pos=6, title="Anexos", rank=1,
                           source="toc", printed="6")]
    run_verdict(pages, chapters=starts)
    assert pages[3].label == "4"
    assert pages[3].label_source == "toc"


def test_the_printed_page_still_outranks_the_contents():
    from scriptor.reflow.chapters import ChapterStart

    pages = [_page(i, str(i)) for i in range(1, 6)]
    starts = [ChapterStart(pos=3, title="Kapitel", rank=1, source="toc",
                           printed="3")]
    run_verdict(pages, chapters=starts)
    assert pages[2].label_source == "printed"
