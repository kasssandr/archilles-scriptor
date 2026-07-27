"""Footnote separation by type size (page model).

Zuckerman prints footnote definitions as ``N. Text`` — a pattern far too
common in running prose to trust as a bare regex. The page model knows more:
the footnote block is set measurably smaller (7.5pt against 9.0pt body) and
sits at the bottom of the page. These tests lock that contract:

  * ``reconstruct`` carries the dominant size of every printed line,
  * ``split_small_type_block`` cuts the trailing small-type block,
  * ``parse_page`` reads ``N.``/``N)`` definitions from a size-verified block,
  * a definition running over the page break is reattached to its note.
"""

from scriptor.page import Box, Line, Span, SourcePage, dumps
from scriptor.reflow.core import attach_continuations, main, parse_page
from scriptor.reflow.footnotes import split_small_type_block
from scriptor.reflow.textlines import reconstruct


def _frag(text, x0, baseline, size=9.0):
    box = Box(x0, baseline - 7.0, x0 + 4.5 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


# ----------------------------------------------------------------------
# reconstruct carries sizes
# ----------------------------------------------------------------------

def test_reconstruct_reports_the_dominant_size_per_printed_line():
    page = SourcePage(index=1, width=300.0, height=400.0, lines=[
        _frag("Brottext in gewohnter Groesse.", 30, 50.0, size=9.0),
        _frag("1. Eine kleine Fussnote.", 30, 380.0, size=7.5),
    ])
    r = reconstruct(page)
    assert r.measured
    assert r.sizes == [9.0, 7.5]


def test_reconstruct_size_is_char_weighted_within_a_printed_line():
    # A short bold 11pt word inside a 9pt line must not drag the line to 11.
    page = SourcePage(index=1, width=300.0, height=400.0, lines=[
        _frag("Ein", 30, 50.0, size=11.0),
        _frag("langer Rest der gedruckten Zeile in neun Punkt.", 60, 50.2, size=9.0),
    ])
    r = reconstruct(page)
    assert r.sizes == [9.0]


def test_passthrough_pages_have_no_sizes_to_offer():
    page = SourcePage(index=1, lines=[Line(spans=[Span("nur Text")])])
    r = reconstruct(page)
    assert not r.measured
    assert r.sizes == [None]


# ----------------------------------------------------------------------
# split_small_type_block
# ----------------------------------------------------------------------

BODY = [
    "Narbonne for seven long years. What new situation impelled the Goth",
    "residents to throw in their fate with the besiegers in the end?",
]
NOTES = [
    "14.  Ut omnes homines eorum legis habeant, tam Romani quam et Salici;",
    "cf. also L. Oelsner, Jahrbuecher unter Koenig Pippin, pp. 410-17.",
]


def test_a_trailing_small_block_with_a_definition_is_cut():
    lines = BODY + NOTES
    sizes = [9.0, 9.0, 7.5, 7.5]
    split = split_small_type_block(lines, sizes, body_size=9.0)
    assert split is not None
    assert split.body == BODY
    assert split.notes == NOTES


def test_a_note_heavy_page_splits_against_the_document_body_size():
    # Footnotes carry more characters than the body here; the page-local
    # dominant size would be the footnote size and see nothing small.
    lines = [BODY[0]] + NOTES + [
        "Jahrbuecher des fraenkischen Reichs 741-752, pp. 20-21 und weiter.",
    ]
    sizes = [9.0, 7.5, 7.5, 7.5]
    assert split_small_type_block(lines, sizes) is None
    split = split_small_type_block(lines, sizes, body_size=9.0)
    assert split is not None
    assert split.body == [BODY[0]]


def test_a_bottom_page_label_stays_with_the_body():
    lines = BODY + NOTES + ["44"]
    sizes = [9.0, 9.0, 7.5, 7.5, 7.5]
    split = split_small_type_block(lines, sizes, body_size=9.0)
    assert split is not None
    assert split.body == BODY + ["44"]
    assert split.notes == NOTES


def test_a_small_block_without_any_definition_is_not_cut():
    # A caption or a small-set quotation is not a footnote block.
    lines = BODY + ["Abb. 3: Der Hafen von Narbonne."]
    sizes = [9.0, 9.0, 7.5]
    assert split_small_type_block(lines, sizes) is None


def test_without_measured_sizes_there_is_no_split():
    assert split_small_type_block(BODY + NOTES, [None] * 4) is None


def test_a_small_line_in_the_middle_of_the_page_is_not_a_footnote_block():
    lines = [BODY[0], "7.  kleine Zeile mitten im Text", BODY[1]]
    sizes = [9.0, 7.5, 9.0]
    assert split_small_type_block(lines, sizes) is None


def test_the_block_may_open_with_the_continuation_of_an_earlier_note():
    lines = BODY + ["setzung der Fussnote von der Vorseite.", "15.  Neue Fussnote."]
    sizes = [9.0, 9.0, 7.5, 7.5]
    split = split_small_type_block(lines, sizes, body_size=9.0)
    assert split is not None
    assert split.notes[0].startswith("setzung")


# ----------------------------------------------------------------------
# parse_page with a size-verified block
# ----------------------------------------------------------------------

def test_parse_page_reads_dot_definitions_from_the_block():
    pg = parse_page(
        "Der Vertrag wurde geschlossen.14 Danach zogen die Heere ab.",
        fn_block=["14.  Capitularia regum francorum ed. A. Boretius."],
    )
    assert pg.footnotes == {14: "Capitularia regum francorum ed. A. Boretius."}
    assert "[14]" in pg.body_lines[0]


def test_parse_page_keeps_the_leading_continuation_for_the_previous_page():
    pg = parse_page(
        "Neuer Seitentext beginnt hier.",
        fn_block=["ende der alten Fussnote.", "15.  Eine neue Fussnote."],
    )
    assert pg.footnotes == {15: "Eine neue Fussnote."}
    assert pg.fn_continuation == "ende der alten Fussnote."


def test_attach_continuations_extends_the_last_note_of_the_previous_page():
    first = parse_page(
        "Text der ersten Seite.9 Weiter im Text.",
        fn_block=["9.  Anfang der langen Fuss-"],
    )
    second = parse_page(
        "Text der zweiten Seite.",
        fn_block=["note, die weiterlaeuft.", "10.  Kurze Fussnote."],
    )
    attach_continuations([first, second])
    assert first.footnotes[9] == "Anfang der langen Fussnote, die weiterlaeuft."
    assert second.fn_continuation is None


# ----------------------------------------------------------------------
# end to end: geometry pages through main
# ----------------------------------------------------------------------

def test_small_type_footnotes_leave_the_running_text(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf", lines=[
        _frag("1", 30, 20.0),
        _frag("Der lange Satz des Brottextes zieht sich ueber die Zeile hin.4", 30, 50.0),
        _frag("Und hier endet der Absatz.", 30, 62.0),
        _frag("4.  Die kleine Fussnote unten auf der Seite.", 30, 380.0, size=7.5),
    ])
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "book.txt"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    assert "[4] Die kleine Fussnote unten auf der Seite." in text
    assert "Absatz. 4." not in text  # the definition no longer bleeds into the body


# ----------------------------------------------------------------------
# a numbered list is prose, not a footnote block
# ----------------------------------------------------------------------

# Regression (EXCITE 35056 p. 19, 11696 pp. 10/20/31): a page whose paragraphs
# open with "1)", "2)" … was read as a footnote block from the first match on.
# With the list starting at line 0 the body came out empty and the whole page
# vanished from the render — 47 of 53 lines lost without a trace. The geometry
# had already spoken: the page carries no small type, so there is no footnote
# block to find, and the bare regex must not overrule that.

_LIST_PAGE_LINES = [
    "1)  Entwicklungspolitische Wirkung. Fuer die Zusammenarbeit mit allen",
    "Partnerlaendern stellt sich zuerst die Frage nach der groessten Wirkung.",
    "2)  Subsidiaritaet. Angesichts zunehmender Leistungsfaehigkeit sollten",
    "Massnahmen schrittweise zurueckgenommen werden.",
]


def test_a_numbered_list_on_a_measured_page_stays_body(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf", lines=[
        _frag(text, 30, 50.0 + 12.0 * i) for i, text in enumerate(_LIST_PAGE_LINES)
    ])
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "book.txt"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    # Nothing may go missing, whatever the list is taken for.
    assert "Entwicklungspolitische Wirkung" in text
    assert "Subsidiaritaet" in text
    assert "Massnahmen schrittweise zurueckgenommen" in text


def test_measured_page_without_a_small_block_has_no_footnotes():
    pg = parse_page("\n".join(_LIST_PAGE_LINES), geometry_verified=True)
    assert pg.footnotes == {}
    assert len(pg.body_lines) == len(_LIST_PAGE_LINES)


def test_the_bare_regex_still_serves_pages_without_geometry():
    # The TXT path has no sizes to consult; there the convention is all we have.
    pg = parse_page("\n".join(_LIST_PAGE_LINES))
    assert set(pg.footnotes) == {1, 2}
