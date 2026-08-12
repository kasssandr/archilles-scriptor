"""Where the front matter ends -- positionally, not by vocabulary.

The design question this answers: a preface is front matter when a further
list follows it, and body text when it leads into the argument. That is a
question about position, and the volume itself answers it twice over -- in its
pagination, and in where it stops printing lists.
"""
from scriptor.reflow.core import Page
from scriptor.reflow.regions import front_matter_zone_end


def _page(label, mode="main", lines=("Ordinary running prose on this page.",)):
    return Page(num=-1, body_lines=list(lines), mode=mode, label=label)


def test_roman_to_arabic_ends_the_zone():
    """Themistios: contents XI-XIII, body from 1. The publisher says it."""
    pages = [_page("xi", "toc"), _page("xii", "toc"), _page("xiii", "toc"),
             _page("1"), _page("2")]
    assert front_matter_zone_end(pages) == 3


def test_a_volume_paginated_throughout_falls_back_to_the_last_list():
    """Bauer: preface on 7, contents 9-16, body from 19. No numeral change.

    The volume has to be long enough for the opening tenth to reach past its
    own front matter -- Bauer runs 348 pages, so the bound sits at 34 and the
    contents ends well inside it. A toy volume of thirty pages would cut the
    zone at three and measure the bound rather than the rule.
    """
    pages = ([_page(str(n), "frontmatter") for n in range(5, 9)]
             + [_page(str(n), "toc") for n in range(9, 17)]
             + [_page(str(n)) for n in range(17, 140)])
    assert front_matter_zone_end(pages) == 12


def test_a_contents_at_the_volume_end_does_not_open_a_zone():
    """Nine of sixteen volumes print their contents last. Without the bound,
    one at 98 % would declare almost the whole book front matter."""
    pages = [_page(str(n)) for n in range(1, 101)]
    pages[97] = _page("98", "toc")
    assert front_matter_zone_end(pages) == 0


def test_no_front_matter_at_all_yields_zero():
    assert front_matter_zone_end([_page(str(n)) for n in range(1, 20)]) == 0


def test_a_single_roman_page_is_not_a_numeral_change():
    """A lone "i" is more often an OCR artefact than a roman numeral; the page
    label module already refuses it below two characters, and so must this."""
    pages = [_page("i"), _page("2"), _page("3"), _page("4")]
    assert front_matter_zone_end(pages) == 0
