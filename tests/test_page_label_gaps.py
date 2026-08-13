"""Pages a volume counts but does not print a folio on.

A chapter opening, a plate, the page facing one: the printer suppresses the
folio, and the page then carries no ``[p. NN]`` marker at all. That is the one
place where a marker may be computed rather than read, because a page between
two printed labels is not guessed — it is enclosed. Page 13 between a printed
12 and a printed 14 is the only thing it can be.

The condition is that the book counts every physical page in the gap: if two
physical pages separate the printed 12 from the printed 14, then the volume
does not have a missing 13, it has an uncounted plate. Over the sixteen corpus
volumes 181 of 190 interior gaps close exactly, and the nine that do not are
precisely the cases a rule without the condition would corrupt -- a year
misread as a label, a script change mid-volume, a double-page scan.

The front edge is counted backwards from the first arabic label: the sequence
has a floor at page 1, so the run is bounded even without a right-hand anchor.
The back edge has neither and is left alone.

A computed label is marked as such (``Page.label_source``), because rules that
draw structural conclusions from a label must not draw them from an inference.
"""

from scriptor.reflow.core import Page, reconcile_page_numbers


def _page(index, label):
    """A page at a physical position, with or without a printed label."""
    return Page(
        num=-1,
        body_lines=["Etwas Text auf dieser Seite."],
        index=index,
        label_bottom=label,
    )


def _labels(pages):
    return [p.label for p in pages]


# ----------------------------------------------------------------------
# the enclosed page
# ----------------------------------------------------------------------

def test_a_single_unprinted_page_between_two_printed_ones_is_filled():
    pages = [_page(1, "11"), _page(2, "12"), _page(3, None), _page(4, "14")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["11", "12", "13", "14"]


def test_a_run_of_unprinted_pages_is_filled():
    # Themistios opens sections without a folio, three in a row at one point.
    pages = [_page(1, "24"), _page(2, None), _page(3, None), _page(4, None), _page(5, "28")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["24", "25", "26", "27", "28"]


def test_the_filled_page_carries_the_ordinal_too():
    # ``num`` orders the pages; a label without it would sort as unnumbered.
    pages = [_page(1, "12"), _page(2, None), _page(3, "14")]
    reconcile_page_numbers(pages)
    assert [p.num for p in pages] == [12, 13, 14]


# ----------------------------------------------------------------------
# where the arithmetic does not close, nothing is invented
# ----------------------------------------------------------------------

def test_an_uncounted_plate_leaves_the_gap_open():
    # Two physical pages, one missing number: the volume does not count them.
    pages = [_page(1, "12"), _page(2, None), _page(3, None), _page(4, "14")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["12", None, None, "14"]


def test_a_double_page_scan_leaves_the_gap_open():
    # Gli Actus Silvestri: one physical sheet carries two printed pages, so the
    # labels count further than the pages do. Four of its gaps look like this.
    pages = [_page(1, "12"), _page(2, None), _page(3, "15")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["12", None, "15"]


def test_a_gap_that_counts_backwards_is_left_alone():
    pages = [_page(1, "40"), _page(2, None), _page(3, "12")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["40", None, "12"]


def test_the_front_is_counted_backwards_from_the_first_arabic_label():
    # Bauer prints "7" on physical page 7; the five pages before it are the
    # title pages, and the volume counts them.
    pages = [_page(i, None) for i in range(1, 7)] + [_page(7, "7")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["1", "2", "3", "4", "5", "6", "7"]


def test_counting_backwards_stops_at_page_one():
    # Themistios prints "2" on physical page 17: exactly one page is reachable,
    # and the roman front matter before it is not touched.
    pages = [_page(i, None) for i in range(14, 17)] + [_page(17, "2")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == [None, None, "1", "2"]


def test_a_script_change_leaves_the_page_between_undecided():
    # Roman "iv", then arabic "3". The page between them is where the volume
    # switches script, and nothing says which side it falls on -- counting
    # backwards from the 3 would claim it for the body on no evidence.
    pages = [_page(1, None), _page(2, "iv"), _page(3, None), _page(4, "3")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == [None, "iv", None, "3"]


def test_a_backwards_run_does_not_start_from_a_roman_label():
    pages = [_page(1, None), _page(2, None), _page(3, "vii"), _page(4, "viii")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == [None, None, "vii", "viii"]


def test_the_tail_is_never_extrapolated():
    pages = [_page(1, "8"), _page(2, "9"), _page(3, None), _page(4, None)]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["8", "9", None, None]


def test_roman_gaps_are_left_open():
    # The roman stretch is the front matter, where an unprinted page is as
    # likely to be uncounted as counted. No corpus volume shows an interior
    # roman gap, so there is nothing here to verify a rule against.
    pages = [_page(1, "vii"), _page(2, None), _page(3, "ix")]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["vii", None, "ix"]


# ----------------------------------------------------------------------
# the rule needs a physical distance to reason about
# ----------------------------------------------------------------------

def test_without_physical_indices_nothing_is_filled():
    # Callers that build pages without an index (older tests, the bare TXT
    # path) state no physical distance, so the gap cannot be shown to close.
    pages = [
        Page(num=-1, body_lines=["Text."], label_bottom=lbl)
        for lbl in ("12", None, "14")
    ]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["12", None, "14"]


def test_the_verdict_reports_how_many_labels_it_computed():
    from scriptor.reflow.pagination.verdict import run_verdict

    pages = [_page(1, "12"), _page(2, None), _page(3, "14")]
    assert run_verdict(pages).computed_count == 1


# ----------------------------------------------------------------------
# it does not disturb what already worked
# ----------------------------------------------------------------------

def test_a_fully_printed_volume_is_untouched():
    pages = [_page(i, str(10 + i)) for i in range(1, 6)]
    reconcile_page_numbers(pages)
    assert _labels(pages) == ["11", "12", "13", "14", "15"]


def test_a_volume_without_any_labels_stays_unlabelled():
    pages = [_page(1, None), _page(2, None), _page(3, None)]
    assert reconcile_page_numbers(pages) == "none"
    assert _labels(pages) == [None, None, None]


# ----------------------------------------------------------------------
# a computed label is marked as one
# ----------------------------------------------------------------------

def test_the_source_of_every_label_is_recorded():
    pages = [_page(1, None), _page(2, "2"), _page(3, None), _page(4, "4")]
    reconcile_page_numbers(pages)
    assert [p.label for p in pages] == ["1", "2", "3", "4"]
    assert [p.label_source for p in pages] == [
        "computed", "printed", "computed", "printed",
    ]


def test_a_computed_one_does_not_start_the_body():
    # assign_modes reads a printed "1" as the start of the main text. Counting
    # backwards gives the title page that label in every volume counted from 1,
    # and acting on it would hand the whole front matter to the body.
    from scriptor.reflow.core import assign_modes

    pages = [_page(1, None), _page(2, None), _page(3, "3")]
    for p in pages:
        p.body_lines = ["Kurze Zeile."]
    reconcile_page_numbers(pages)
    assert pages[0].label == "1" and pages[0].label_source == "computed"
    assign_modes(pages)
    assert pages[0].mode == "frontmatter"
