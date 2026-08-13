"""Detection no longer decides: the verdict does, and what it rejects comes back.

parse_page used to delete the line it read as a page label -- before anything
had checked whether it was one. Gli Actus lost the chapter number "2" that way,
Carlomagno a footnote number. The line is still lifted out of the page (leaving
it in place would let the footnote block on the TXT path swallow it), but it is
remembered with the position it held, and a candidate the verdict does not
confirm is put back.
"""

from scriptor.reflow.core import (
    parse_page,
    reconcile_page_numbers,
    restore_rejected_folios,
)


def _paged(texts):
    pages = []
    for i, t in enumerate(texts, start=1):
        p = parse_page(t)
        p.index = i
        pages.append(p)
    return pages


def test_a_label_line_is_remembered_with_its_place():
    page = parse_page("Ein Satz auf der Seite.\n42")
    assert [(c.label, c.edge, c.line_index) for c in page.folio_candidates] == [
        ("42", "bottom", 1)
    ]


def test_both_edges_are_recorded_as_candidates():
    page = parse_page("77\nEin Satz.\n42")
    assert {c.edge for c in page.folio_candidates} == {"top", "bottom"}


def test_a_single_line_page_yields_one_candidate_not_two():
    # The bottom candidate and the top candidate would otherwise be the same
    # line, counted twice.
    page = parse_page("42")
    assert len(page.folio_candidates) == 1


def test_a_confirmed_label_leaves_the_body_alone():
    pages = _paged([f"Ein Satz auf der Seite.\n{n}" for n in (11, 12, 13)])
    reconcile_page_numbers(pages)
    assert restore_rejected_folios(pages) == 0
    assert all(p.body_lines == ["Ein Satz auf der Seite."] for p in pages)


def test_a_rejected_candidate_comes_back_into_the_body():
    # The chapter number "2" on a chapter opening: by the sequence the volume
    # prints 47 there, so "2" is not the folio -- and it is not lost either.
    pages = _paged(["Text.\n45", "Text.\n46", "2\nText.", "Text.\n48"])
    reconcile_page_numbers(pages)
    assert restore_rejected_folios(pages) == 1
    assert pages[2].body_lines == ["2", "Text."]
    assert pages[2].label == "47"


def test_a_folio_sharing_a_running_head_takes_the_whole_line_with_it():
    # "146 WILHELM HEIL": the label is "146", but what leaves the page is the
    # head. Putting only the number back would strand a running title in the
    # body of every page of the volume.
    pages = _paged([f"{n} WILHELM HEIL\nEin Satz." for n in (146, 147, 148)])
    reconcile_page_numbers(pages)
    assert restore_rejected_folios(pages) == 0
    assert all(p.body_lines == ["Ein Satz."] for p in pages)
    assert [p.label for p in pages] == ["146", "147", "148"]


def test_the_footnote_block_is_unaffected_by_the_candidate():
    # On the TXT path the footnote block is found by convention, and a folio
    # left standing at the foot of the page would be read as part of the last
    # note.
    page = parse_page("Haupttext der Seite.\n1) Eine Anmerkung.\n42")
    assert page.footnotes == {1: "Eine Anmerkung."}
    assert page.label_bottom == "42"
