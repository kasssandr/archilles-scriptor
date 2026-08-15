"""The contents link: the producer stating where an entry goes.

The contents witness of stage 3 places an entry by searching the body for its
title, which can fail in both directions -- the title may not be found, or found
in the wrong place. A link removes that step: the file itself resolves the
destination to a page, so the only thing left to read is the number the contents
line prints.

Measured over the corpus, that is rare: of eighteen volumes exactly one carries
contents links (Libros). Where it happens it is the most direct evidence about a
page reference a PDF can hold, which is why it outweighs every other witness
except the page printing the number itself.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.verdict import run_verdict
from scriptor.reflow.pagination.witnesses import link_observations


def _page(index, label=None):
    return Page(num=-1, body_lines=["Text der Seite."], index=index,
                label_bottom=label)


# ── what the witness states ──────────────────────────────────────────

def test_the_link_says_which_position_carries_the_printed_number():
    # "Kapitel 1 .......... 31" links to physical page 51: the volume prints 31
    # on its 51st page.
    obs = link_observations({9: [(51, "Kapitel 1 .......... 31")]})
    assert [(o.pos, o.label, o.source) for o in obs] == [(51, "31", "link")]


def test_the_witness_outweighs_a_searched_contents_entry():
    from scriptor.reflow.pagination.witnesses import LINK_WEIGHT, TOC_WEIGHT

    assert LINK_WEIGHT > TOC_WEIGHT


def test_a_line_without_a_printed_number_states_nothing():
    assert link_observations({9: [(51, "Kapitel 1")]}) == []


def test_a_leading_number_is_not_the_page_reference():
    # "1. La storia degli studi" — a chapter number, and the line names no page.
    assert link_observations({9: [(51, "1. La storia degli studi")]}) == []


def test_the_dots_between_title_and_number_do_not_matter():
    obs = link_observations({9: [(51, "Kapitel 1 . . . . . . 31")]})
    assert [o.label for o in obs] == ["31"]


def test_a_link_pointing_at_its_own_page_states_nothing():
    # The contents entry for the contents itself, or a link the extraction
    # mis-resolved. Either way it cannot tell us what another page prints.
    assert link_observations({9: [(9, "Índice .......... 9")]}) == []


def test_a_roman_reference_is_not_read_at_all():
    # Roman letters are ordinary letters, and reflow/toc.py reads contents
    # entries as arabic for that reason: "La storia degli studi" ends in "di",
    # which is a well-formed roman 501. The price is a contents entry pointing
    # into a roman front matter, and it is the same price the contents parser
    # has always paid.
    assert link_observations({4: [(10, "Premessa .......... xi")]}) == []


def test_the_witness_carries_its_reason():
    (o,) = link_observations({9: [(51, "Kapitel 1 .......... 31")]})
    assert "9" in o.why and "31" in o.why


# ── what it does to the verdict ──────────────────────────────────────

def test_a_link_settles_a_page_that_prints_nothing():
    # The chapter opening prints no folio; the contents links to it and states
    # the number. Nothing else in the volume knows it.
    pages = [_page(i) for i in range(1, 6)] + [_page(6, "31"), _page(7, "32")]
    run_verdict(pages, links={1: [(4, "Kapitel 1 .......... 29")]})
    assert pages[3].label == "29"


def test_the_page_still_wins_where_it_prints_its_own_number():
    pages = [_page(1, "27"), _page(2, "28"), _page(3, "29"), _page(4, "30")]
    run_verdict(pages, links={1: [(3, "Kapitel 1 .......... 77")]})
    assert [p.label for p in pages] == ["27", "28", "29", "30"]


def test_without_links_the_verdict_is_unchanged():
    pages = [_page(1, "27"), _page(2, "28"), _page(3), _page(4, "30")]
    run_verdict(pages)
    assert [p.label for p in pages] == ["27", "28", "29", "30"]
