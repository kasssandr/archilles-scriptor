"""Where the front matter ends -- positionally, not by vocabulary.

The design question this answers: a preface is front matter when a further
list follows it, and body text when it leads into the argument. That is a
question about position, and the volume itself answers it twice over -- in its
pagination, and in where it stops printing lists.
"""
from scriptor.reflow.core import Page
from scriptor.reflow.regions import (
    assign_regions,
    front_matter_zone_end,
    region_of_heading,
)


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


# ── the zone in use ──────────────────────────────────────────────────


def test_a_preface_before_the_contents_is_front_matter():
    """Bauer's case, confirmed by the operator: the preface reports how the
    dissertation came about and is printed ahead of the table of contents."""
    pages = ([_page("7", "frontmatter", ("Vorwort",))]
             + [_page(str(n), "toc", ("Inhaltsverzeichnis",)) for n in range(9, 17)]
             + [_page(str(n)) for n in range(17, 140)])
    assign_regions(pages)
    assert pages[0].region == "preface"


def test_a_preface_after_the_front_matter_is_body_text():
    """Where it no longer sits in the opening zone it leads into the argument,
    and §4.4 would rather carry a stray page of thanks than lose a chapter.

    The heading has to be one the vocabulary actually matches, or the test
    passes without ever reaching the rule it is about.
    """
    assert region_of_heading("Vorwort") == "preface"
    pages = [_page(str(n)) for n in range(1, 60)]
    pages[40] = _page("41", "main", ("Vorwort",))
    assign_regions(pages)
    assert pages[40].region == "main"


def test_the_contents_still_follows_a_preface():
    """Regression: the mode fallback fires only while `main` is running, from
    a defect where a bare "Índice" set `toc` for every page after it. A
    preface running ahead of the contents would hide it under that condition.

    The contents pages deliberately carry NO recognisable heading -- otherwise
    the vocabulary would name them and the fallback, which is what this test
    is about, would never be reached.
    """
    pages = ([_page("7", "frontmatter", ("Vorwort",))]
             + [_page(str(n), "toc", ("Kapitel 1. Die Aneignung .... 17",))
                for n in range(9, 17)]
             + [_page(str(n)) for n in range(17, 140)])
    assign_regions(pages)
    assert pages[0].region == "preface"
    assert pages[1].region == "contents"


def test_a_bibliography_is_not_overwritten_by_a_late_preface_word():
    """The zone bounds `preface` in both directions: an apparatus running at
    the end of the volume keeps its name."""
    pages = [_page(str(n)) for n in range(1, 40)]
    pages[30] = _page("31", "main", ("Literaturverzeichnis",))
    pages[31] = _page("32", "main", ("Ringraziamenti",))
    assign_regions(pages)
    assert pages[31].region == "bibliography"


def _lizzi():
    """Lizzi Testa's opening, as measured: half title, imprint, two pages of
    contents, then the two-page "Premessa" -- and no further list behind it.

    A hundred pages, so the opening tenth reaches past the front matter and
    the bound is not what the test measures.
    """
    pages = ([_page(None, "frontmatter", ("LE TRASFORMAZIONI DELLE ELITES",)),
              _page(None, "main", ("© Copyright 2006 by L'ERMA di BRETSCHNEIDER",)),
              _page(None, "toc", ("INDICE", "G. BONAMENTE, Premessa 7")),
              _page(None, "main", ("Indice generale", "P. PORENA, Trasformazioni")),
              _page(None, "main", ("PREMESSA", "Il Convegno Internazionale")),
              _page(None, "main", ("Premessa", "to dal MIUR e dalle Università"))]
             + [_page(str(n)) for n in range(9, 103)])
    return pages


def test_a_preface_directly_behind_the_contents_is_still_front_matter():
    """Lizzi Testa: the contents is printed first and the "Premessa" follows
    it. The zone stopped at the last *list*, which is exactly the page the
    preface opens on -- so the volume's own front matter was one position too
    short, every time, and the preface counted as body text.

    The rule the operator gave holds either way round: what makes this front
    matter is that it adjoins the front matter, not which of the two comes
    first.
    """
    pages = _lizzi()
    assert front_matter_zone_end(pages) == 6
    assign_regions(pages)
    assert [p.region for p in pages[4:6]] == ["preface", "preface"]


def test_a_preface_ends_where_the_front_matter_ends():
    """The other half of the same rule, and the more expensive half. `preface`
    is not apparatus, so none of the closing rules of §4.4 reach it: opened and
    left to run, it took 438 of Lizzi Testa's 497 pages -- every page up to the
    bibliography. A preface is as long as the zone it stands in.
    """
    pages = _lizzi()
    assign_regions(pages)
    assert pages[6].region == "main"
    assert all(p.region != "preface" for p in pages[6:])


def test_a_preface_inside_the_opening_tenth_still_needs_to_adjoin_the_zone():
    """The zone may not talk itself into existence. A volume that heads a page
    "Vorwort zur Neuausgabe" early on -- but behind pages of running text --
    has said nothing about where its body begins, and if a preface could
    extend the zone from anywhere inside the opening tenth, every such page
    would licence itself.
    """
    pages = [_page(str(n), "frontmatter") for n in range(1, 3)]
    pages += [_page(str(n)) for n in range(3, 101)]
    pages[7] = _page("8", "main", ("Vorwort",))
    assert front_matter_zone_end(pages) == 2
    assign_regions(pages)
    assert pages[7].region == "main"


def test_a_contents_known_only_from_its_running_head_still_ends_the_zone():
    """Bauer's case, and the reason the first cut of this function failed on
    it: its table of contents is not `mode=toc` at all. The mode never fires,
    and the eight pages are recognised solely by the running head
    "Inhaltsverzeichnis" that every one of them carries.

    Without that signal the zone closed after the five title pages -- one
    position ahead of the preface on printed 7, which therefore counted as
    body text and kept the name `front-matter`.
    """
    pages = ([_page(str(n), "frontmatter") for n in range(1, 6)]
             + [_page("7", "main", ("Vorwort",))]
             + [_page(str(n), "main", ("19",)) for n in range(9, 17)]
             + [_page(str(n)) for n in range(17, 200)])
    heads = ([None] * 6 + ["Inhaltsverzeichnis"] * 8
             + [None] * (len(pages) - 14))

    assert front_matter_zone_end(pages, page_headers=heads) == 14

    assign_regions(pages, page_headers=heads)
    assert pages[5].region == "preface"
