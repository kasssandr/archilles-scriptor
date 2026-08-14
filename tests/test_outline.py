"""The PDF outline: chapter titles the document states, believed where the page confirms.

Zuckerman's catalogue carries 20 outline entries ("2 The Surrender of Narbonne
to the Franks in 759" -> physical page 56). That knowledge settles two things
the heuristics guess at today: where a chapter heading begins (the title is
glued to the first paragraph), and which running heads are chapter titles —
whose trailing year ("… in 759") the edge-number preservation would otherwise
keep as a phantom page number.

Junk filtering follows Archilles (`pdf_extractor._build_page_toc_map`): fewer
than three entries, all pointing at one page, or scanner-artifact titles mean
the outline is not believed at all. A believed entry still only acts where the
page itself shows the title (OCR-tolerant match).
"""

import json

import pymupdf

from scriptor.extract import pymupdf_backend
from scriptor.reflow.outline import (
    OutlineEntry,
    chapter_headings,
    credible,
    load_outline,
    match_prefix_lines,
    strip_running_titles,
)


# ----------------------------------------------------------------------
# the backend writes what the catalogue states
# ----------------------------------------------------------------------

def test_extract_writes_the_outline_sidecar(tmp_path):
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page(width=300, height=400).insert_text((20, 60), "Text.", fontsize=9)
    doc.set_toc([[1, "Vorwort", 1], [1, "1 Der Anfang", 2], [1, "2 Das Ende", 4]])
    pdf = tmp_path / "buch.pdf"
    doc.save(pdf)

    pymupdf_backend.extract(pdf, tmp_path / "pages")

    entries = load_outline(tmp_path / "pages")
    assert entries == [
        OutlineEntry(level=1, title="Vorwort", page=1),
        OutlineEntry(level=1, title="1 Der Anfang", page=2),
        OutlineEntry(level=1, title="2 Das Ende", page=4),
    ]


def test_no_outline_means_no_sidecar_and_an_empty_load(tmp_path):
    doc = pymupdf.open()
    doc.new_page(width=300, height=400).insert_text((20, 60), "Text.", fontsize=9)
    pdf = tmp_path / "buch.pdf"
    doc.save(pdf)

    pymupdf_backend.extract(pdf, tmp_path / "pages")

    assert not (tmp_path / "pages" / "outline.json").exists()
    assert load_outline(tmp_path / "pages") == []


# ----------------------------------------------------------------------
# junk filtering (Archilles rules)
# ----------------------------------------------------------------------

def _entry(title, page, level=1):
    return OutlineEntry(level=level, title=title, page=page)


def test_a_real_outline_is_credible():
    assert credible([_entry("Vorwort", 1), _entry("1 Anfang", 5), _entry("2 Ende", 9)])


def test_fewer_than_three_entries_are_not_believed():
    assert not credible([_entry("Vorwort", 1), _entry("1 Anfang", 5)])


def test_an_outline_pointing_at_one_page_is_not_believed():
    assert not credible([_entry("a", 1), _entry("b", 1), _entry("c", 1)])


def test_scanner_artifact_titles_are_not_believed():
    assert not credible([_entry("scan 001", 1), _entry("scan 002", 5), _entry("Echt", 9)])


# ----------------------------------------------------------------------
# the page confirms the title
# ----------------------------------------------------------------------

CHAPTER_PAGE = [
    "2",
    "The Surrender of Narbonne ",
    "to the Franks in 759",
    "1 he fall of the mighty Saracen citadel of Narbonne to the Franks in ",
]
TITLE = "2 The Surrender of Narbonne to the Franks in 759"


def test_the_title_is_found_across_number_and_two_title_lines():
    assert match_prefix_lines(CHAPTER_PAGE, TITLE) == 3


def test_ocr_noise_in_the_page_is_tolerated():
    noisy = ["2", "The Surrénder of Narbonne ", "to the Franks in 759", "1 he fall…"]
    assert match_prefix_lines(noisy, TITLE) == 3


def test_a_page_that_does_not_show_the_title_gives_no_match():
    assert match_prefix_lines(["Ganz anderer Text hier oben.", "Und weiter."], TITLE) is None


def test_chapter_headings_maps_verified_level1_entries_to_their_page():
    entries = [
        _entry("Inhalt", 1),
        _entry(TITLE, 2),
        _entry("3 Nie gedruckt", 3),
    ]
    pages = [
        ["Inhaltsverzeichnis…"],
        CHAPTER_PAGE,
        ["Hier steht etwas voellig anderes.", "Der Titel fehlt."],
    ]
    headings = chapter_headings(entries, pages)
    assert headings == {2: (TITLE, 3)}


# ----------------------------------------------------------------------
# chapter running heads vanish without leaving a phantom folio
# ----------------------------------------------------------------------

def test_a_chapter_running_head_is_removed_without_preserving_its_year():
    pages = [[
        "The Surrender of Narbonne to the Franks in 759",
        "40",
        "Aniane, is mutilated and, for the period 717 through 777, suffers an ",
    ]]
    stripped = strip_running_titles(pages, [TITLE])
    assert stripped[0] == [
        "40",
        "Aniane, is mutilated and, for the period 717 through 777, suffers an ",
    ]


def test_a_folio_sharing_the_head_line_survives_as_a_label_line():
    pages = [[
        "44 The Surrender of Narbonne to the Franks in 759",
        "Narbonne for seven long years.",
    ]]
    stripped = strip_running_titles(pages, [TITLE])
    assert stripped[0] == ["44", "Narbonne for seven long years."]


def test_body_text_below_the_head_region_is_never_touched():
    pages = [[
        "Erste Zeile der Seite ohne Kopf.",
        "Zweite Zeile.",
        "Dritte Zeile.",
        "The Surrender of Narbonne to the Franks in 759",
    ]]
    assert strip_running_titles(pages, [TITLE]) == pages


# ----------------------------------------------------------------------
# end to end: heading in the output, running head gone
# ----------------------------------------------------------------------

def test_a_verified_chapter_start_becomes_a_heading(tmp_path):
    from scriptor.page import Box, Line, Span, SourcePage, dumps
    from scriptor.reflow.core import main

    def _frag(text, baseline, size=9.0):
        box = Box(30, baseline - 7.0, 30 + 4.5 * len(text), baseline + 2.0)
        return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    prose = [
        "Der lange Satz des Brottextes zieht sich weit ueber die",
        "Zeile hin und noch weiter, denn die Seite soll wie ganz",
        "gewoehnliche Prosa aussehen, Zeile um Zeile gleich lang,",
        "damit die Modus-Erkennung sie als Haupttext einordnet und",
        "nicht als Vorspann. Hier endet der erste lange Absatz.",
    ]
    chapter_page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf",
                              label="36", lines=[
        _frag("2", 30.0, size=16.0),
        _frag("Die Uebergabe von Narbonne", 50.0, size=15.0),
        *[_frag(t, 70.0 + i * 12) for i, t in enumerate(prose)],
        # The chapter opening prints its folio at the foot, as many volumes do.
        # Two readings rather than one, because a lone one no longer establishes
        # a numbering system (FitParams.min_attested).
        _frag("36", 380.0),
    ])
    next_page = SourcePage(index=2, width=300.0, height=400.0, source="pymupdf",
                           label="37", lines=[
        _frag("Die Uebergabe von Narbonne", 20.0),
        _frag("37", 21.0),
        _frag("Der Text der Folgeseite steht hier und redet weiter.", 50.0),
        *[_frag(t, 62.0 + i * 12) for i, t in enumerate(prose)],
    ])
    (pages_dir / "00000001.json").write_text(dumps(chapter_page), encoding="utf-8")
    (pages_dir / "00000002.json").write_text(dumps(next_page), encoding="utf-8")
    (pages_dir / "outline.json").write_text(json.dumps([
        {"level": 1, "title": "Vorspann", "page": 1},
        {"level": 1, "title": "2 Die Uebergabe von Narbonne", "page": 1},
        {"level": 1, "title": "3 Anhang", "page": 2},
    ]), encoding="utf-8")

    out = tmp_path / "book.md"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    assert "# 2 Die Uebergabe von Narbonne" in text
    # The title is no longer glued to the first paragraph…
    assert "Narbonne Der lange erste Satz" not in text
    # …and the running head of the next page is gone, its folio kept as label.
    assert "[p. 37] Der Text der Folgeseite" in text


def test_a_heading_cut_from_the_page_still_triggers_the_mode():
    # The outline confirmed "Contents" and cut it off the page — the TOC
    # trigger must still see it, or the contents page reflows as prose.
    from scriptor.reflow.core import Page, assign_modes

    toc_page = Page(num=5, body_lines=[
        "1. The Jews of Septimania  3",
        "2. The Surrender of Narbonne  36",
        "3. The Prominence of Septimanian Jewry  47",
    ])
    toc_page.heading = "Contents"
    assign_modes([toc_page])
    assert toc_page.mode == "toc"
