"""The reader of the prepared format, where a consumer may import it from.

parse_prepared moved here out of eval/ (the benchmark's workshop); load_bundle adds
what travels beside the master -- the metadata block and the pagination sidecar
(spec §4.1, §6.3). Archilles reads a bundle through this module instead of keeping
a second copy of the grammar.
"""
import json

import pytest

from scriptor.document import (
    MIN_WORDING_WORDS,
    Bundle,
    find_snippet,
    load_bundle,
    master_headings,
    normalize,
    parse_prepared,
)
from scriptor.reflow.regions import FORMAT_VERSION, render_metadata_block

BODY = """[p. xiv] Ein Vorwort, römisch gezählt.

[region: bibliography]

[p. 1] Ein Satz mit Anker [^1].

[^1]: Die Note.
"""


def _sidecar(pages, version=1):
    return json.dumps({"version": version,
                       "profile": {"edge": "bottom", "attested": 0.5, "band": None},
                       "segments": [], "pages": pages, "rejected": []})


def _bundle(tmp_path, *, block=True, sidecar=None, body=BODY):
    master = tmp_path / "book.md"
    head = render_metadata_block("scientific", "bottom edge, 50% of pages attested")
    master.write_text((head + "\n\n" if block else "") + body, encoding="utf-8")
    if sidecar is not None:
        (tmp_path / "book.md.pagination.json").write_text(sidecar, encoding="utf-8")
    return master


PAGES = [
    {"pos": 3, "label": "xiv", "source": "printed", "confidence": 1.0},
    {"pos": 5, "label": "1", "source": "computed", "confidence": 0.5},
]


# the move -------------------------------------------------------------------

def test_the_eval_adapter_uses_this_reader_not_a_copy():
    from scriptor.eval import adapters
    assert adapters.parse_prepared is parse_prepared


def test_parse_prepared_reads_what_it_read_before():
    doc = parse_prepared(render_metadata_block() + "\n\n" + BODY)
    assert [lbl for lbl, _ in doc.page_marks] == ["xiv", "1"]
    assert [name for name, _ in doc.region_marks] == ["bibliography"]
    assert doc.footnotes[0].definition == "Die Note."


# definitions over several lines ---------------------------------------------

def test_a_definition_keeps_its_continuation_lines():
    """A definition runs on over the lines that follow it, up to a blank line --
    Pandoc's lazy continuation, and the spec promises valid Pandoc. Scriptor
    writes such definitions where a note's text kept a line break (three of
    thirty library volumes, 39 lines); a reader that stops at the first line
    drops the rest without a trace."""
    text = ("Ein Satz [^1] und noch einer [^2].\n\n"
            "[^1]: Humboldt, Kosmos, https://example.org/kosmos\n"
            "(letzter Zugriff: 27.02.23).\n\n"
            "[^2]: Ebenda.\n")
    doc = parse_prepared(text)
    assert [f.definition for f in doc.footnotes] == [
        "Humboldt, Kosmos, https://example.org/kosmos\n(letzter Zugriff: 27.02.23).",
        "Ebenda.",
    ]
    assert doc.body == "Ein Satz [^1] und noch einer [^2]."


def test_a_definition_ends_where_the_next_one_begins():
    doc = parse_prepared("Ein Satz [^1][^2].\n\n[^1]: Erste.\n[^2]: Zweite.\n")
    assert [f.definition for f in doc.footnotes] == ["Erste.", "Zweite."]


# the bundle -----------------------------------------------------------------

def test_a_bundle_carries_its_declaration(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert isinstance(b, Bundle)
    assert b.format_version == FORMAT_VERSION
    assert b.chunking_strategy == "scientific"
    assert b.pagination == "bottom edge, 50% of pages attested"
    assert b.text.endswith(BODY)


def test_physical_page_and_source_come_from_the_sidecar(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert b.physical_page_of("xiv") == 3          # roman label, verbatim
    assert b.source_of("xiv") == "printed"
    assert b.physical_page_of("1") == 5
    assert b.source_of("1") == "computed"


def test_a_label_the_sidecar_does_not_know_has_no_page(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert b.physical_page_of("73, ed. Buber") is None
    assert b.source_of("73, ed. Buber") is None


def test_without_a_sidecar_the_bundle_still_reads(tmp_path):
    """A missing sidecar is no error: the text is whole (spec §3), only the
    physical page is unknown -- and unknown is None, never a guess."""
    b = load_bundle(_bundle(tmp_path))
    assert b is not None
    assert b.pages == []
    assert b.physical_page_of("xiv") is None
    assert b.source_of("xiv") is None


def test_a_sidecar_that_found_no_printed_number_is_a_normal_bundle(tmp_path):
    # Seven of thirty library volumes in M1 (EPUB conversions, scans of spreads):
    # the sidecar exists and its page list is empty.
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar([]), body="Text ohne Seitenzahl.\n"))
    assert b is not None and b.pages == []
    assert b.resolve_marks(parse_prepared(b.text)) == []


def test_a_master_without_a_block_is_not_a_bundle(tmp_path):
    assert load_bundle(_bundle(tmp_path, block=False, sidecar=_sidecar(PAGES))) is None


def test_a_block_without_format_version_is_not_a_bundle(tmp_path):
    master = tmp_path / "book.md"
    master.write_text("---\nchunking_strategy: basic\n---\n\n" + BODY, encoding="utf-8")
    assert load_bundle(master) is None


def test_chunking_strategy_defaults_to_basic(tmp_path):
    # Spec §4.1: every field is optional, and the absent strategy is basic.
    master = tmp_path / "book.md"
    master.write_text(f"---\nformat_version: {FORMAT_VERSION}\n---\n\n" + BODY, encoding="utf-8")
    assert load_bundle(master).chunking_strategy == "basic"


def test_a_sidecar_of_an_unknown_version_is_refused(tmp_path):
    with pytest.raises(ValueError, match="version"):
        load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES, version=2)))


def test_an_unknown_source_is_passed_through(tmp_path):
    """Spec §6.3: the list has grown twice. The consumer treats a value it does
    not know as asserted -- so it must see the value, not a replacement."""
    pages = [{"pos": 3, "label": "xiv", "source": "ocr-verified", "confidence": 0.9}]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages)))
    assert b.source_of("xiv") == "ocr-verified"


# labels that repeat ---------------------------------------------------------

REPEATING = """[p. 1] Erster Teil, erste Seite.

[p. 2] Erster Teil, zweite Seite.

[p. 1] Zweiter Teil, erste Seite.

[p. 2] Zweiter Teil, zweite Seite.
"""

REPEATING_PAGES = [
    {"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
    {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0},
    {"pos": 9, "label": "1", "source": "catalogue", "confidence": 1.0},
    {"pos": 10, "label": "2", "source": "printed", "confidence": 1.0},
]


def test_a_label_that_repeats_has_no_single_page(tmp_path):
    """A volume in parts restarts its numbering (the corpus has one with five
    pages labelled 1). Asked by label alone, the answer is not one page."""
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(REPEATING_PAGES), body=REPEATING))
    assert b.physical_page_of("1") is None
    assert b.source_of("1") is None


def test_each_marker_finds_its_own_page_in_reading_order(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(REPEATING_PAGES), body=REPEATING))
    resolved = b.resolve_marks(parse_prepared(b.text))
    assert [(e.pos, e.source) for e in resolved] == [
        (3, "printed"), (4, "printed"), (9, "catalogue"), (10, "printed")]


def test_a_page_without_a_marker_does_not_shift_the_rest(tmp_path):
    # A labelled page with no text of its own gets no marker in the master;
    # the next marker with that label belongs to a later page, not to it.
    body = "[p. 1] Erster Teil.\n\n[p. 1] Zweiter Teil.\n\n[p. 2] Weiter.\n"
    pages = [
        {"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
        {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0},   # leer, ohne Marker
        {"pos": 9, "label": "1", "source": "printed", "confidence": 1.0},
        {"pos": 10, "label": "2", "source": "printed", "confidence": 1.0},
    ]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages), body=body))
    assert [e.pos for e in b.resolve_marks(parse_prepared(b.text))] == [3, 9, 10]


def test_a_marker_the_sidecar_does_not_know_resolves_to_nothing(tmp_path):
    """Book text that looks like a marker -- 'Midrash Tanhuma B 1 [p. 73, ed.
    Buber]' in Josephus -- names no page of this volume. It resolves to None and
    leaves the markers after it untouched."""
    body = "[p. 1] Midrash Tanhuma B 1 [p. 73, ed. Buber], und weiter.\n\n[p. 2] Fort.\n"
    pages = [{"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
             {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0}]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages), body=body))
    resolved = b.resolve_marks(parse_prepared(b.text))
    assert [e.pos if e else None for e in resolved] == [3, None, 4]


# the '#' lines of a master (spec §4.2) -----------------------------------

HEADINGS_BODY = """[p. 22] Der letzte Satz des Kapitels davor.

# I. Aneignung als Rechtsbegriff

## A. Der Begriff

[p. 23] Der erste Satz des Kapitels.

[region: bibliography]

###### *Ein tiefer Titel*

[p. 24] Ein Eintrag.
"""


def test_a_heading_stands_on_the_page_the_marker_after_it_opens():
    doc = parse_prepared(HEADINGS_BODY)
    heads = master_headings(doc)
    assert [(h.marks, h.text) for h in heads] == [
        (1, "I. Aneignung als Rechtsbegriff"),
        (2, "A. Der Begriff"),
        (6, "*Ein tiefer Titel*"),
    ]
    # Both headings open p. 23 -- they stand before its marker, not on p. 22.
    assert [h.page for h in heads] == ["23", "23", "24"]


def test_a_heading_inside_a_page_keeps_that_page():
    doc = parse_prepared("[p. 5] Ein Satz.\n\n## Mitten drin\n\nNoch ein Satz.\n")
    assert [h.page for h in master_headings(doc)] == ["5"]


def test_a_heading_knows_the_region_it_stands_in():
    doc = parse_prepared(HEADINGS_BODY)
    assert [h.region for h in master_headings(doc)] == ["", "", "bibliography"]


def test_seven_hashes_are_a_paragraph_not_a_heading():
    doc = parse_prepared("[p. 1] Satz.\n\n####### Keine Überschrift\n")
    assert master_headings(doc) == []


# the address: page, occurrence, wording (P-B1) ---------------------------

ADDRESS_BODY = """[p. 1] Auf der ersten Seite des ersten Teils steht dieser eine lange Satz.

[p. 2] Die zweite Seite trägt einen eigenen, hinreichend langen Satz für sich allein.

[p. 1] Auf der ersten Seite des zweiten Teils steht ein ganz anderer langer Satz.
"""

ADDRESS_PAGES = [
    {"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
    {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0},
    {"pos": 9, "label": "1", "source": "catalogue", "confidence": 1.0},
]

FIRST = "Auf der ersten Seite des ersten Teils steht dieser eine lange Satz."
MIDDLE = "Die zweite Seite trägt einen eigenen, hinreichend langen Satz für sich allein."
SECOND = "Auf der ersten Seite des zweiten Teils steht ein ganz anderer langer Satz."


def _address(tmp_path, *, body=ADDRESS_BODY, pages=ADDRESS_PAGES, structure=None):
    if structure is not None:
        (tmp_path / "book.md.structure.json").write_text(
            json.dumps({"version": 1, "chapter_level": 1, "schemes": [],
                        "headings": [{"depth": d, "title": t} for d, t in structure],
                        "unplaced": [], "rejected": []}), encoding="utf-8")
    return load_bundle(_bundle(tmp_path, body=body,
                               sidecar=_sidecar(pages) if pages is not None else None))


def test_the_text_match_lives_with_the_reader_and_eval_imports_it():
    """``find_snippet`` was the benchmark's; it is the match §B.7 of the wiki
    concept means and the one ``locate`` uses. It moves here, where a consumer
    may import it, and ``eval/normalize.py`` reads it from here (pattern S1)."""
    from scriptor.eval import normalize as eval_normalize
    assert eval_normalize.find_snippet is find_snippet
    assert eval_normalize.normalize is normalize


def test_page_text_is_the_nth_page_carrying_the_label(tmp_path):
    b = _address(tmp_path)
    assert "ersten Teils" in b.page_text("1")
    assert "zweiten Teils" in b.page_text("1", 2)
    assert b.page_text("1", 3) is None
    assert b.page_text("7") is None


def test_locate_searches_the_named_page_and_nowhere_else(tmp_path):
    """The wording is a checksum, not a pointer (Befund §1.2): where the page
    does not carry it, the answer is None -- never the same words elsewhere."""
    b = _address(tmp_path)
    loc = b.locate(SECOND, page="1", occurrence=2)
    assert (loc.page, loc.occurrence, loc.pos) == ("1", 2, 9)
    assert b.doc.body[loc.start:loc.end] == SECOND
    assert not loc.ambiguous and not loc.proposed
    assert b.locate(SECOND, page="1") is None
    assert b.locate(MIDDLE, page="1") is None


def test_without_a_page_the_document_answers_with_its_first_hit(tmp_path):
    b = _address(tmp_path)
    loc = b.locate(SECOND)
    assert (loc.page, loc.occurrence, loc.pos) == ("1", 2, 9)
    # An occurrence names a page's repetition; without a page it names nothing.
    with pytest.raises(ValueError):
        b.locate(SECOND, occurrence=2)


def test_the_nearest_page_that_carries_the_wording_is_a_proposal(tmp_path):
    """Spec §4.7: a consumer may offer the nearest page as a proposal, never as
    a repair. Three pages in both directions, the page after first."""
    b = _address(tmp_path)
    prop = b.nearest(MIDDLE, page="1")
    assert (prop.page, prop.occurrence, prop.proposed) == ("2", 1, True)
    assert b.doc.body[prop.start:prop.end] == MIDDLE
    assert b.nearest(FIRST, page="2").page == "1"
    assert b.nearest("Ein Wortlaut, den dieser Band nirgends druckt, nicht einmal hier",
                     page="1") is None


def test_a_wording_standing_twice_on_its_page_is_ambiguous(tmp_path):
    """P-M2: nine of 1437 addresses found the wrong place at eight words, all of
    them on a page that prints the wording twice. None of them was silent."""
    twice = "Ein Satz, der auf dieser Seite zweimal steht, wortgleich und lang genug."
    b = _address(tmp_path, body=f"[p. 1] {twice}\n\nUnd hier noch einmal: {twice}\n",
                 pages=ADDRESS_PAGES[:1])
    loc = b.locate(twice, page="1")
    assert loc.ambiguous
    assert b.doc.body[loc.start:loc.end] == twice


def test_an_ocr_variant_of_the_wording_is_found(tmp_path):
    b = _address(tmp_path, pages=[ADDRESS_PAGES[0]],
                 body="[p. 1] Die Aneignung des Beſitzes war für die Straßburger "
                      "Bürger ein wich-\ntiger Vorgang.\n")
    assert b.locate("Die Aneignung des Besitzes war für die Strassburger Bürger "
                    "ein wichtiger Vorgang.", page="1") is not None


def test_markers_hashes_and_escapes_belong_to_no_wording(tmp_path):
    """A new production renumbers the note anchors and may level a heading
    differently: that changes hashes and marker, and no word. The first P-M2 run
    lost five of eighty matches to '#' against '####' alone."""
    b = _address(tmp_path, pages=[ADDRESS_PAGES[0]],
                 body="[p. 1] Ein Satz mit einem Anker [^1] und einem \\*Sternchen\\* "
                      "darin, lang genug.\n\n"
                      "#### Die Aneignung als Rechtsbegriff im späten Mittelalter "
                      "und in der Neuzeit\n\n"
                      "[^1]: Die Note.\n")
    assert b.locate("Ein Satz mit einem Anker und einem *Sternchen* darin, lang genug.",
                    page="1") is not None
    assert b.locate("Die Aneignung als Rechtsbegriff im späten Mittelalter und in "
                    "der Neuzeit", page="1") is not None


def test_a_wording_shorter_than_the_minimum_is_refused(tmp_path):
    """Eight words, measured (P-M2 §3): shorter ones find the wrong place, longer
    ones do not fit in their paragraph."""
    b = _address(tmp_path)
    short = " ".join(FIRST.split()[:MIN_WORDING_WORDS - 1])
    with pytest.raises(ValueError):
        b.locate(short, page="1")
    with pytest.raises(ValueError):
        b.nearest(short, page="1")


def test_a_master_without_a_sidecar_locates_without_a_physical_page(tmp_path):
    b = _address(tmp_path, pages=None)
    loc = b.locate(FIRST, page="1")
    assert loc.page == "1" and loc.pos is None


def test_a_wording_is_cut_from_one_paragraph(tmp_path):
    """Measured (P-M2, Briefing §8): a wording that runs over a paragraph
    boundary breaks as soon as a heading is inserted there. The address was cut
    badly; the page is not stale. A thousand wordings cut across Bauer's
    headings failed for no other reason."""
    body = ("[p. 1] Ein Absatz mit genau so vielen Wörtern, dass er eine "
            "Adresse gerade noch trägt.\n\n"
            "## Eine Überschrift dazwischen\n\n"
            "Und danach geht der Text weiter, mit genügend Wörtern für eine "
            "zweite Adresse.\n")
    b = _address(tmp_path, body=body, pages=ADDRESS_PAGES[:1])
    at = b.doc.body.index("Ein Absatz")
    wording = b.wording_at(at)
    assert wording == "Ein Absatz mit genau so vielen Wörtern, dass"
    assert b.locate(wording, page="1").start == at
    # From the marker on, the marker is not a word of the wording.
    assert b.wording_at(0) == wording
    # Three words from the paragraph's end there is no address, and the heading
    # behind it lends none.
    assert b.wording_at(b.doc.body.index("gerade noch")) is None


def test_a_wording_stops_at_the_page_it_stands_on(tmp_path):
    """A wording over a page boundary is never found: ``locate`` reads one page
    and the rest of it stands on the next. Thirty-three of 899 wordings cut
    across Bauer's page markers were stale for that reason and no other."""
    body = ("[p. 1] Ein erster Satz auf dieser Seite, und dann: der Rest ohne "
            "Punkt [p. 2]{#p-2} läuft in die nächste Seite hinein.\n")
    b = _address(tmp_path, body=body, pages=ADDRESS_PAGES[:2])
    assert b.wording_at(b.doc.body.index("Ein erster")) == \
        "Ein erster Satz auf dieser Seite, und dann:"
    assert b.wording_at(b.doc.body.index("der Rest")) is None   # vier bis zur Grenze
    # Wäre er über die Grenze geschnitten, fände ihn keine der beiden Seiten.
    over = "der Rest ohne Punkt läuft in die nächste"
    assert b.locate(over, page="1") is None and b.locate(over, page="2") is None
    # Ein Offset mitten im Marker beginnt den Wortlaut hinter ihm, nie mit
    # seinem Rest ("2]{#p-2} läuft in die ...").
    inside = b.doc.body.index("[p. 2]{#p-2}") + 4
    assert b.wording_at(inside, words=3) == "läuft in die"


# the section a position stands in ----------------------------------------

SECTION_BODY = """[p. 1] Vor dem Kapitel.

# I. Das Kapitel

[p. 2] Der erste Satz des Kapitels, lang genug für eine Adresse auf dieser Seite.

###### *Ein tiefer Titel*

[p. 3] Der Text des tiefen Abschnitts, ebenfalls lang genug für eine Adresse.

###### Ein Unterabschnitt

[p. 4] Und weiter im Text, auch hier mit genügend Wörtern für eine Adresse.

###### Der nächste Titel

[p. 5] Das Ende des Masters, mit hinreichend vielen Wörtern für eine Adresse.
"""

SECTION_PAGES = [{"pos": i, "label": str(i), "source": "printed", "confidence": 1.0}
                 for i in range(1, 6)]

# What the master's six hashes cannot say (spec §6.5, Briefing §8.3): the
# subsection is deeper than the title above it, though both print six.
SECTION_DEPTHS = [(1, "I. Das Kapitel"), (7, "*Ein tiefer Titel*"),
                  (8, "Ein Unterabschnitt"), (7, "Der nächste Titel")]


def test_a_section_reaches_to_the_next_heading_of_its_own_depth(tmp_path):
    b = _address(tmp_path, body=SECTION_BODY, pages=SECTION_PAGES,
                 structure=SECTION_DEPTHS)
    text = b.doc.body[slice(*b.section_span("3", "*Ein tiefer Titel*"))]
    assert "Ein Unterabschnitt" in text
    assert "Der nächste Titel" not in text
    assert b.section_span("3", "Ein Titel, der dort nicht steht") is None
    assert b.section_span("4", "*Ein tiefer Titel*") is None


def test_without_a_structure_sidecar_the_hashes_say_the_depth(tmp_path):
    b = _address(tmp_path, body=SECTION_BODY, pages=SECTION_PAGES)
    text = b.doc.body[slice(*b.section_span("3", "*Ein tiefer Titel*"))]
    assert "Ein Unterabschnitt" not in text


def test_the_last_section_reaches_to_the_end_of_the_master(tmp_path):
    b = _address(tmp_path, body=SECTION_BODY, pages=SECTION_PAGES,
                 structure=SECTION_DEPTHS)
    span = b.section_span("5", "Der nächste Titel")
    assert span[1] == len(b.doc.body)


def test_node_at_names_the_heading_a_position_stands_under(tmp_path):
    b = _address(tmp_path, body=SECTION_BODY, pages=SECTION_PAGES,
                 structure=SECTION_DEPTHS)
    loc = b.locate("Und weiter im Text, auch hier mit genügend Wörtern für eine Adresse.",
                   page="4")
    assert b.node_at(loc.start).text == "Ein Unterabschnitt"
    assert b.node_at(0) is None
