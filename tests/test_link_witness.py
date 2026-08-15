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


def test_a_reference_with_a_rectangle_of_its_own_is_read_bare():
    # Josephus and Jesus links the printed page separately, at the right margin.
    obs = link_observations({10: [(30, "13")]})
    assert [(o.pos, o.label) for o in obs] == [(30, "13")]


def test_a_title_whose_last_word_is_a_number_states_nothing():
    # "Kapitel 1" is a title, not an entry with a page reference. A contents
    # line that means a page sets it apart -- that is what a leader is for.
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


def _volume_with_a_catalogue(links=None):
    """Ten pages carried by a catalogue that has only partly earned its hearing.

    Three pages print a folio; the catalogue matches two of them, so it weighs
    0.67 -- below a link, above nothing. That is Josephus and Jesus in
    miniature, where the catalogue is right about the volume and agrees with 4 %
    of what the pages themselves were read as printing.
    """
    pages = []
    for i in range(1, 11):
        printed = {1: "21", 2: "22", 3: "99"}.get(i)
        p = _page(i, printed)
        p.backend_label = str(20 + i)
        pages.append(p)
    run_verdict(pages, links=links or {})
    return pages


def test_the_source_names_the_link_and_not_a_weaker_witness():
    # Josephus and Jesus: the catalogue and the contents links agree on 321
    # pages, and every label was credited to the catalogue. The field is
    # supposed to name the *strongest* witness that confirmed the label, and a
    # link the producer resolved outweighs a catalogue that agrees with 4 % of
    # what the volume prints.
    pages = _volume_with_a_catalogue({1: [(7, "Kapitel 1 ....... 27")]})
    assert pages[6].label == "27"
    assert pages[6].label_source == "link"
    assert pages[7].label_source == "catalogue"


def test_a_linked_page_is_better_attested_than_an_unlinked_one():
    # Confidence measures corroboration. A link is a printed cross-reference --
    # the number was read off a contents line the volume printed -- so it
    # corroborates, where a catalogue only asserts.
    linked = _volume_with_a_catalogue({1: [(7, "Kapitel 1 ....... 27")]})
    bare = _volume_with_a_catalogue()
    assert linked[6].label_confidence > bare[6].label_confidence
