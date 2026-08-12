"""Region convention of PREPARED_FORMAT_SPEC §4.4.

Two things are tested apart, because the spec keeps them apart: what a region
is *called* (the vocabulary, consumer-facing) and where it *ends* (the closing
rule, which is what keeps a false positive from swallowing a book).
"""
import pytest

from scriptor.reflow.core import Page, assign_modes, render_book
from scriptor.reflow.regions import (
    REGION_NAMES,
    assign_regions,
    region_of_heading,
    render_metadata_block,
)


# ── Vocabulary ───────────────────────────────────────────────────────

def test_german_headings_without_number_prefix():
    # Bauer (Nomos) prints it plain — today's trigger demanded "NN. Literatur".
    assert region_of_heading("Literaturverzeichnis") == "bibliography"
    assert region_of_heading("Literatur") == "bibliography"
    assert region_of_heading("Quellen- und Literaturverzeichnis") == "bibliography"
    assert region_of_heading("Personenregister") == "index"
    assert region_of_heading("Abkürzungsverzeichnis") == "abbreviations"


def test_number_prefix_still_accepted():
    # Hechberger numbers its back matter; that must keep working.
    assert region_of_heading("13. Literatur") == "bibliography"
    assert region_of_heading("14. Personenregister") == "index"
    assert region_of_heading("11. Abkürzungsverzeichnis") == "abbreviations"


def test_english_headings():
    # Zuckerman, Anglo-Norman studies.
    assert region_of_heading("Selected Bibliography") == "bibliography"
    assert region_of_heading("List of Abbreviations") == "abbreviations"
    assert region_of_heading("ABBREVIATIONS") == "abbreviations"
    assert region_of_heading("Index") == "index"
    assert region_of_heading("Works Cited") == "bibliography"
    assert region_of_heading("Appendix IV") == "appendix"


def test_romance_and_latin_headings():
    assert region_of_heading("Bibliographie") == "bibliography"
    assert region_of_heading("Bibliografia") == "bibliography"
    assert region_of_heading("Índice de nombres") == "index"
    assert region_of_heading("Index nominum") == "index"
    assert region_of_heading("Abréviations") == "abbreviations"
    assert region_of_heading("Afkortingen") == "abbreviations"


def test_cyrillic_headings():
    assert region_of_heading("Библиография") == "bibliography"
    assert region_of_heading("Указатель имён") == "index"
    assert region_of_heading("Список сокращений") == "abbreviations"


def test_running_prose_is_never_a_region():
    assert region_of_heading("Die Literatur der Zeit war reich an Beispielen.") is None
    assert region_of_heading("Ein Index ist eine geordnete Liste von Begriffen.") is None
    assert region_of_heading("") is None
    # "Vorwort" stood here until 0.3.0 gave it a name of its own. What takes
    # its place is a heading deliberately left out of the vocabulary: imprint,
    # glossary, chronology, tables and maps have one attestation between them
    # across sixteen volumes, and one attestation is not a name.
    assert region_of_heading("Impressum") is None


def test_every_vocabulary_value_is_a_spec_name():
    for line in ("Literaturverzeichnis", "Index", "Abkürzungen", "Anmerkungen",
                 "Anhang", "Selected Bibliography"):
        name = region_of_heading(line)
        assert name is None or name in REGION_NAMES


# ── Closing rule ─────────────────────────────────────────────────────

def _prose(n=12, width=70):
    return Page(-1, ["x" * width for _ in range(n)], {})


def _entries(*lines):
    return Page(-1, list(lines), {})


def test_apparatus_runs_to_the_end_of_the_document():
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Literaturverzeichnis", "Ahlberg, H., Kommentar, 2019"))
    pages.append(_entries("Bauer, E., Aneignung, 2020", "Cariou v. Prince, 2013"))
    assign_modes(pages)
    assign_regions(pages)
    assert [p.region for p in pages[-2:]] == ["bibliography", "bibliography"]


def test_prose_after_an_apparatus_heading_reverts_to_main():
    """Braunfels: 'Abkürzungen:' sits inside an essay, mid-volume.

    Without a closing rule this one line would mark the remaining 150 pages
    of running text as apparatus — the failure §4.4 calls silent loss.
    """
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Abkürzungen:", "MGH = Monumenta Germaniae Historica"))
    pages.extend(_prose() for _ in range(4))
    assign_modes(pages)
    assign_regions(pages)
    assert [p.region for p in pages[-4:]] == ["main"] * 4


def test_one_prose_page_does_not_end_a_bibliography():
    # A dense bibliography page can look like prose; it takes two in a row.
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Bibliography", "Aerts, W., Study, 2003"))
    pages.append(_prose())
    pages.append(_entries("Zeller, K., Werk, 1998"))
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-1].region == "bibliography"


def test_a_confirmed_chapter_heading_ends_an_apparatus():
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Abkürzungsverzeichnis", "MGH = Monumenta"))
    nxt = _prose()
    nxt.heading = "Kapitel 4: Die Reichsteilung"
    pages.append(nxt)
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-1].region == "main"


def test_second_apparatus_heading_switches_region():
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Selected Bibliography", "Aaron b. Jacob, Sefer, 1901"))
    pages.append(_entries("Index", "Aachen, 38; Narbonne, 88"))
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-2].region == "bibliography"
    assert pages[-1].region == "index"


def test_front_matter_and_contents_come_from_the_mode():
    fm = Page(-1, ["Titelei", "Verlag Karlsruhe"], {})
    toc = Page(-1, ["Inhaltsverzeichnis", "Vorwort 7", "Kapitel 1 19"], {})
    body = _prose()
    pages = [fm, toc, body]
    assign_modes(pages)
    assign_regions(pages)
    assert fm.region == "front-matter"
    assert toc.region == "contents"
    assert body.region == "main"


def test_unmarked_document_is_all_main():
    pages = [_prose() for _ in range(4)]
    assign_modes(pages)
    assign_regions(pages)
    assert all(p.region == "main" for p in pages)


# ── Running head as a region signal ──────────────────────────────────

def test_running_head_names_the_region_on_every_page():
    """Zuckerman: 33 bibliography pages, each headed 'Selected Bibliography'.

    The heading appears once; the running head repeats per page and is the
    stronger evidence — it has the contrast a repeated marker needs, because
    only the apparatus pages carry it.
    """
    pages = [_prose() for _ in range(3)] + [_prose() for _ in range(4)]
    heads = [None, None, None,
             "Selected Bibliography", "Selected Bibliography",
             "Selected Bibliography", "Selected Bibliography"]
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages] == ["main"] * 3 + ["bibliography"] * 4


def test_running_head_outlasts_the_prose_rule():
    # Bibliography pages that measure as prose stay bibliography while the
    # running head keeps saying so.
    pages = [_prose() for _ in range(2)] + [_prose() for _ in range(4)]
    heads = [None, None] + ["Index"] * 4
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-4:]] == ["index"] * 4


def test_running_head_that_names_nothing_is_not_a_signal():
    # A book-title running head must neither open nor close a region.
    pages = [_prose() for _ in range(2)]
    pages.append(_entries("Bibliography", "Aerts, W., Study, 2003"))
    pages.append(_entries("Zeller, K., Werk, 1998"))
    heads = ["A Jewish Princedom", "A Jewish Princedom",
             "A Jewish Princedom", "A Jewish Princedom"]
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-2:]] == ["bibliography"] * 2


def test_page_headers_of_wrong_length_are_ignored():
    # Defensive: a caller passing a mismatched list must not shift regions
    # silently onto the wrong pages.
    pages = [_prose() for _ in range(4)]
    assign_modes(pages)
    assign_regions(pages, page_headers=["Index"])
    assert all(p.region == "main" for p in pages)


# ── Emitting the marker (§4.4) and the metadata block (§4.1) ─────────

def _rendered(pages, fmt="md"):
    assign_modes(pages)
    assign_regions(pages)
    text, _audit = render_book(pages, threshold=40, fmt=fmt)
    return text


def test_marker_is_emitted_where_the_region_changes():
    pages = [_prose() for _ in range(3)]
    pages.append(_entries("Literaturverzeichnis", "Ahlberg, H., Kommentar, 2019"))
    text = _rendered(pages)
    assert "[region: bibliography]" in text


def test_marker_is_emitted_once_per_region_not_per_page():
    pages = [_prose() for _ in range(2)]
    pages.append(_entries("Bibliography", "Aerts, W., Study, 2003"))
    pages.append(_entries("Zeller, K., Werk, 1998"))
    pages.append(_entries("Meyer, A., Buch, 2001"))
    text = _rendered(pages)
    assert text.count("[region: bibliography]") == 1


def test_marker_stands_on_a_line_of_its_own():
    pages = [_prose() for _ in range(2)]
    pages.append(_entries("Bibliography", "Aerts, W., Study, 2003"))
    text = _rendered(pages)
    assert any(ln.strip() == "[region: bibliography]" for ln in text.split("\n"))


def test_no_marker_where_no_region_was_recognised():
    # Nothing recognised means no claim — the document stays as it was.
    pages = [_prose() for _ in range(4)]
    text = _rendered(pages)
    assert "[region:" not in text


def test_txt_format_carries_no_markers():
    # The TXT profile is the plain-reading profile; structure markup is md only.
    pages = [_prose() for _ in range(2)]
    pages.append(_entries("Bibliography", "Aerts, W., Study, 2003"))
    text = _rendered(pages, fmt="txt")
    assert "[region:" not in text


def test_metadata_block_is_valid_pandoc_yaml():
    block = render_metadata_block(chunking_strategy="basic")
    lines = block.split("\n")
    assert lines[0] == "---"
    assert "format_version:" in block
    assert "chunking_strategy: basic" in block
    assert lines[-1] == "---" or lines[-2] == "---"


def test_metadata_block_declares_the_spec_version():
    from scriptor.reflow.regions import FORMAT_VERSION
    assert FORMAT_VERSION in render_metadata_block()
    # semver, so a consumer can compare it
    assert len(FORMAT_VERSION.split(".")) == 3


def test_metadata_block_can_be_stripped_back_off():
    from scriptor.reflow.regions import strip_metadata_block
    body = "[p. 1] Der erste Absatz.\n\n[p. 2] Der zweite.\n"
    assert strip_metadata_block(render_metadata_block() + "\n\n" + body) == body


def test_stripping_leaves_a_blockless_document_alone():
    from scriptor.reflow.regions import strip_metadata_block
    body = "[p. 1] Ein Absatz ohne jeden Vorspann.\n"
    assert strip_metadata_block(body) == body


def test_stripping_spares_a_horizontal_rule_further_down():
    # A --- inside the text is a rule, not a metadata block.
    from scriptor.reflow.regions import strip_metadata_block
    body = "[p. 1] Absatz.\n\n---\n\n[p. 2] Nach dem Trenner.\n"
    assert strip_metadata_block(body) == body


def test_eval_adapter_ignores_the_metadata_block():
    # The harness measures the text, not the declaration: offsets must count
    # from the first word either way.
    from scriptor.eval.adapters import parse_prepared
    body = "[p. 1] Ein Satz mit Note [^1].\n\n[^1]: Die Note.\n"
    bare = parse_prepared(body)
    withblock = parse_prepared(render_metadata_block() + "\n\n" + body)
    assert withblock.page_marks == bare.page_marks
    assert [f.anchor_offset for f in withblock.footnotes] == [
        f.anchor_offset for f in bare.footnotes
    ]


# ── The tail rule ────────────────────────────────────────────────────

def test_apparatus_in_the_last_quarter_survives_prose_pages():
    """Bauer: 20 densely set bibliography pages that measure as prose.

    Closing on prose would end the region after one page. In the last
    quarter of a volume the prose rule is suspended, because it exists to
    protect running text and there is almost none left to protect.
    """
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("Literaturverzeichnis", "Ahlberg, H., Kommentar, 2019"))
    pages.extend(_prose() for _ in range(5))
    assign_modes(pages)
    assign_regions(pages)
    assert [p.region for p in pages[-5:]] == ["bibliography"] * 5


def test_apparatus_mid_volume_still_closes_on_prose():
    # Braunfels stays protected: half a book is a lot to lose.
    pages = [_prose() for _ in range(20)]
    pages.append(_entries("Abkürzungen:", "MGH = Monumenta Germaniae Historica"))
    pages.extend(_prose() for _ in range(20))
    assign_modes(pages)
    assign_regions(pages)
    assert [p.region for p in pages[-20:]] == ["main"] * 20


def test_front_matter_abbreviations_still_close_on_prose():
    # An abbreviation list at the front is short and the body follows it.
    pages = [Page(-1, ["Titelei"], {})]
    pages.append(_entries("List of Abbreviations", "MGH = Monumenta"))
    pages.extend(_prose() for _ in range(30))
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-1].region == "main"


def test_a_foreign_running_head_closes_a_region_even_in_the_tail():
    """Anglo-Norman: an essay's own APPENDIX, 81% into a collective volume.

    Sixty-eight pages of further essays follow it. The running head is what
    tells them apart from a bibliography: it names an essay, not a region, so
    the pages under it belong to a structure that is not apparatus. The volume
    sets its heads alternating — series title verso, essay title recto — and
    only the essay title counts as evidence (the series title covers the whole
    book and distinguishes nothing).
    """
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("APPENDIX", "[I] Edward rex. Ubi Harold dux"))
    pages.extend(_prose() for _ in range(9))
    heads = ["Anglo-Norman Studies XXIII"] * 31 + [
        "Anglo-Norman Studies XXIII" if i % 2 else "The Bayeux Tapestry"
        for i in range(9)
    ]
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-8:]] == ["main"] * 8


def test_a_region_naming_running_head_holds_through_the_tail():
    # Zuckerman: 'Selected Bibliography' over every page of it.
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("Selected Bibliography", "Aaron b. Jacob, Sefer, 1901"))
    pages.extend(_prose() for _ in range(9))
    heads = [None] * 30 + ["Selected Bibliography"] * 10
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-9:]] == ["bibliography"] * 9


def test_headless_tail_pages_still_hold_the_region():
    # Bauer prints no running head over its bibliography — absence of a head
    # must not be read as a foreign one.
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("Literaturverzeichnis", "Ahlberg, H., Kommentar, 2019"))
    pages.extend(_prose() for _ in range(5))
    heads = [None] * 36
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-5:]] == ["bibliography"] * 5


# ── Vocabulary gaps found by measuring further volumes (2026-08-10) ──

def test_french_index_with_an_adjective():
    # Guilhiermoz 1902 prints INDEX ALPHABÉTIQUE, repeated as a running head.
    assert region_of_heading("INDEX ALPHABÉTIQUE") == "index"
    assert region_of_heading("ÍNDICE ANALÍTICO") == "index"


def test_the_open_complement_needs_capitals():
    """A complement the vocabulary does not list is only read off a capitalised
    line — which is how the volumes measured here print their indexes. Set in
    lower case the same words are indistinguishable from a sentence, and §4.4
    says to stay silent then."""
    assert region_of_heading("INDEX ALPHABÉTIQUE") == "index"
    assert region_of_heading("Index alphabétique nach Sachgruppen") is None


def test_french_index_with_a_multi_word_complement():
    # Bresson has four of them; only two matched a "des <one word>" pattern.
    assert region_of_heading("INDEX DES NOMS DE PERSONNES") == "index"
    assert region_of_heading("INDEX DES SOURCES") == "index"
    assert region_of_heading("INDEX DES LIEUX") == "index"
    assert region_of_heading("INDEX DES PERSONNAGES") == "index"


def test_a_sentence_opening_with_index_is_still_not_a_region():
    # The generic complement must not swallow prose.
    assert region_of_heading("Index ist eine geordnete Liste.") is None
    assert region_of_heading("Index of this kind was unknown then.") is None


def test_contents_has_its_own_vocabulary():
    # A table of contents at the *end* of a volume (Pückert, Guilhiermoz):
    # assign_modes only sees it as a mode, the region needs the name too.
    assert region_of_heading("TABLE DES MATIÈRES") == "contents"
    assert region_of_heading("Inhaltsübersicht") == "contents"
    assert region_of_heading("Inhaltsverzeichnis") == "contents"
    assert region_of_heading("Contents") == "contents"
    assert region_of_heading("Sommaire") == "contents"


def test_an_excursus_is_not_an_appendix():
    # Pückert's "Erster Excurs." is an argument inside the book, not apparatus.
    assert region_of_heading("Erster Excurs.") is None
    assert region_of_heading("Excurs") is None


def test_contents_closes_like_an_apparatus_region():
    # It is not apparatus, but it must not run on either: a contents region
    # that never closed would hide every chapter behind it.
    pages = [_prose() for _ in range(4)]
    pages.append(_entries("Inhaltsübersicht", "Erstes Kapitel 7", "Zweites Kapitel 19"))
    pages.extend(_prose() for _ in range(4))
    assign_modes(pages)
    assign_regions(pages)
    assert [p.region for p in pages[-4:]] == ["main"] * 4


def test_a_singular_note_is_not_a_notes_section():
    """Baynes prints NOTE over a publisher's preliminary remark.

    An apparatus is titled in the plural; the singular is nearly always
    something else, so it is not in the vocabulary.
    """
    assert region_of_heading("NOTE") is None
    assert region_of_heading("Notes") == "notes"
    assert region_of_heading("Anmerkungen") == "notes"


def test_a_running_head_on_half_the_volume_is_not_a_signal():
    """Bresson prints the volume title on every verso and the section title on
    every recto. Read naively, the verso head closes the region on every other
    page and the marker flickers.

    This is Archilles' rule 1 — a marker every unit carries is convention, not
    meaning — applied to running heads: one that covers half the volume
    distinguishes nothing and is ignored as evidence.
    """
    pages = [_prose() for _ in range(20)]
    pages.append(_entries("INDEX DES LIEUX", "Athènes, 44; Sparte, 91"))
    pages.extend(_prose() for _ in range(9))
    # verso: volume title; recto: the index title
    heads = ["Parenté et société"] * 21
    for i in range(21, 30):
        heads.append("Parenté et société" if i % 2 else "INDEX DES LIEUX")
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-9:]] == ["index"] * 9


def test_a_rare_running_head_still_closes_a_region():
    # Anglo-Norman: essay titles appear on a few pages each and stay evidence.
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("APPENDIX", "[I] Edward rex. Ubi Harold dux"))
    pages.extend(_prose() for _ in range(9))
    heads = ["Anglo-Norman Studies XXIII"] * 31 + ["The Bayeux Tapestry"] * 9
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-9:]] == ["main"] * 9


def test_a_heading_may_end_in_a_full_stop():
    """Pückert 1899 prints "Inhaltsübersicht." and "Erster Excurs." — setting
    a heading with a closing stop is ordinary in older typography."""
    assert region_of_heading("Inhaltsübersicht.") == "contents"
    assert region_of_heading("Literaturverzeichnis.") == "bibliography"
    assert region_of_heading("Register.") == "index"
    # and it still does not turn a sentence into a heading
    assert region_of_heading("Die Literatur der Zeit war reich.") is None


def test_a_heading_survives_an_ocr_artefact_at_its_end():
    """Guilhiermoz's running head reads "INDEX ALPHABÉTIQUE ·" — the printed
    full stop came back from OCR as a middle dot. The line is otherwise exact,
    and refusing it costs nine pages of index."""
    assert region_of_heading("INDEX ALPHABÉTIQUE ·") == "index"
    assert region_of_heading("Register,") == "index"
    assert region_of_heading("Literaturverzeichnis;") == "bibliography"


# ── Italian and Spanish, measured on six volumes (2026-08-10) ────────

def test_bare_indice_is_a_table_of_contents_not_an_index():
    """The word divides the languages. English, German, French and Latin call
    the back-of-book register "Index"; Italian and Spanish call the *table of
    contents* "Indice"/"Índice" and name the register with a complement —
    "Indice dei nomi", "Índice onomástico". Reading the bare word as an index
    mislabels the front matter of every Italian and Spanish volume."""
    assert region_of_heading("ÍNDICE") == "contents"
    assert region_of_heading("Indice") == "contents"
    assert region_of_heading("Index") == "index"


def test_indice_with_a_complement_is_the_register():
    assert region_of_heading("ÍNDICE ONOMÁSTICO") == "index"
    assert region_of_heading("INDICE ONOMÁSTICO") == "index"   # OCR drops the accent
    assert region_of_heading("Indice dei nomi") == "index"
    assert region_of_heading("Índice analítico") == "index"


def test_spanish_appendix_words():
    # Callaey heads his appendices ANEXOS and Apéndice I/II/III.
    assert region_of_heading("ANEXOS") == "appendix"
    assert region_of_heading("ANEXO 1") == "appendix"
    assert region_of_heading("Apéndice I") == "appendix"
    assert region_of_heading("Apéndice III") == "appendix"


def test_spanish_and_italian_bibliography_forms():
    assert region_of_heading("BIBLIOGRAFÍA SELECTA") == "bibliography"
    assert region_of_heading("bibliografía") == "bibliography"
    assert region_of_heading("Bibliografia") == "bibliography"


def test_a_heading_broken_by_non_breaking_spaces():
    # Barbiero's PDF sets its headings with NBSP between the words.
    assert region_of_heading("INDICE\xa0\xa0DELLE\xa0\xa0ILLUSTRAZIONI") == "index"


def test_a_volume_title_is_recognised_by_its_span_not_its_count():
    """Callaey's verso head — author and title — appears on roughly a third of
    the pages, because chapter openings carry none. Counting occurrences puts
    it under any sane threshold and it closes the appendix on every other page.

    What separates it from a section head is not how often it occurs but how
    far it reaches: a volume title spans the whole book, a section title
    clusters. That is Archilles' rule 1 measured properly — look for contrast,
    and a head that stretches end to end draws no contrast anywhere.
    """
    pages = [_prose() for _ in range(60)]
    pages[40] = _entries("ANEXOS", "El Libro acerca del Templo de Salomón")
    heads: list[str | None] = [None] * 60
    for i in range(0, 60, 3):          # volume title, spread thin but end to end
        heads[i] = "Eduardo Callaey / La masonería"
    for i in (40, 42, 44):             # section title, clustered
        heads[i] = "ANEXOS"
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    # No holes: the pages between two ANEXOS heads belong to the appendix, and
    # the verso volume title must not punch them back out to main.
    assert [p.region for p in pages[40:45]] == ["appendix"] * 5


def test_a_section_head_that_clusters_still_closes_a_region():
    # An essay title confined to its own pages remains evidence.
    pages = [_prose() for _ in range(40)]
    pages[30] = _entries("APPENDIX", "[I] Edward rex. Ubi Harold dux")
    heads: list[str | None] = [None] * 40
    for i in range(31, 40):
        heads[i] = "The Bayeux Tapestry"
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[31:40]] == ["main"] * 9


def test_a_heading_set_over_two_lines():
    """Callaey sets ÍNDICE / ONOMÁSTICO on two lines. Read line by line the
    first one says "contents", which is right for the bare word and wrong
    here — sixteen pages of register mislabelled."""
    page = Page(-1, ["ÍNDICE", "ONOMÁSTICO", "A", "Aarón: 58, 81."], {})
    pages = [_prose() for _ in range(6)] + [page]
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-1].region == "index"


def test_two_line_reading_does_not_invent_regions():
    # Joining lines must not turn ordinary prose into a heading.
    page = Page(-1, ["Der Index", "ist eine geordnete Liste von Begriffen."], {})
    pages = [_prose() for _ in range(6)] + [page]
    assign_modes(pages)
    assign_regions(pages)
    assert pages[-1].region == "main"


def test_a_full_stop_inside_a_word_is_an_ocr_artefact():
    """Lizzi Testa's running head arrives as "Bibliogra.fia" — a stop dropped
    into the middle of the word. Thirty-five pages of bibliography hang on it.

    Between two letters a full stop is not punctuation, so it is folded away.
    One at a word boundary is left alone, where it may well be an abbreviation.
    """
    assert region_of_heading("Bibliogra.fia") == "bibliography"
    assert region_of_heading("Regis.ter") == "index"
    assert region_of_heading("INDICE DEl NOMI") == "index"   # I read as l
    # a stop that ends a word still ends it
    assert region_of_heading("Vgl. dazu die Literatur der Zeit") is None


def test_a_running_head_that_extends_the_region_name():
    """Santa-Aguilar opens ANEXO 1 and then heads every page of it
    "ANEXO 1. ACCIONES VIOLENTAS" — the section title with its subtitle.

    Read whole, that head is in no vocabulary, so it counted as foreign and
    closed the very region it names. A head is therefore also tried up to its
    first separator, which is where a title ends and its subtitle begins.
    """
    from scriptor.reflow.regions import region_of_running_head
    assert region_of_running_head("ANEXO 1. ACCIONES VIOLENTAS") == "appendix"
    assert region_of_running_head("Bibliografia — opere citate") == "bibliography"
    assert region_of_running_head("ANEXO 1") == "appendix"
    # and a volume title still names nothing
    assert region_of_running_head("Eduardo Callaey / La masonería") is None
    assert region_of_running_head("Anglo-Norman Studies XXIII") is None


def test_the_mode_does_not_reopen_a_region_that_is_already_running():
    """Callaey's index alternates: recto heads "ÍNDICE ONOMÁSTICO", verso the
    volume title. assign_modes sets `toc` on the page that opens the index and
    keeps it for every page after, so the mode fallback claimed each verso for
    `contents` and the region flickered index/contents page by page.

    A mode is the coarsest evidence there is. It may name a page that has no
    region of its own; it may not overrule one that is already running.
    """
    pages = [_prose() for _ in range(4)]
    opener = Page(-1, ["ÍNDICE", "ONOMÁSTICO", "A", "Aarón: 58, 81."], {})
    pages.append(opener)
    pages.extend(Page(-1, ["Bermejo: 21.", "Bernardo: 44."], {}) for _ in range(4))
    assign_modes(pages)
    # the reflow keeps `toc` on every page after the trigger
    assert pages[-1].mode == "toc"
    assign_regions(pages)
    assert [p.region for p in pages[4:]] == ["index"] * 5


def test_portuguese_apparatus_forms():
    """Silveira (USP) heads his back matter "Fontes e bibliografia" and letters
    his appendices "Anexo A"; Siqueira/Soares close with "Índice de Nomes e
    Pseudônimos". None of the three were in the table."""
    assert region_of_heading("Fontes e bibliografia") == "bibliography"
    assert region_of_heading("Referências bibliográficas") == "bibliography"
    assert region_of_heading("Anexo A") == "appendix"
    assert region_of_heading("Apêndice B") == "appendix"
    assert region_of_heading("Índice de Nomes e Pseudônimos") == "index"
    assert region_of_heading("Índice de nomes") == "index"


def test_a_lettered_appendix_does_not_swallow_a_sentence():
    assert region_of_heading("Anexo a esta carta folgte ein Verzeichnis") is None


def test_a_control_character_does_not_hide_a_heading():
    """Asclepios (AUP) carries "Literatuur" plus a backspace character in its
    running head — an extraction artefact, not text. Control and format
    characters are dropped before matching; nothing in a printed heading is
    invisible."""
    assert region_of_heading("Literatuur\x08") == "bibliography"
    assert region_of_heading("Bibliografie​") == "bibliography"
    assert region_of_heading("﻿Register") == "index"


def test_french_and_portuguese_complements_of_several_words():
    # Pouderon: "Index des textes cités" (and set with double spaces).
    assert region_of_heading("Index  des  textes cités") == "index"
    assert region_of_heading("Index des auteurs modernes") == "index"
    # Comemoração dos mortos: "Abreviaturas do índice".
    assert region_of_heading("Abreviaturas do índice") == "abbreviations"
    assert region_of_heading("Abreviaturas e siglas") == "abbreviations"


def test_the_tail_rule_does_not_depend_on_how_the_region_opened():
    """Pouderon's bibliography opens on a running head and then loses it —
    the pages after carry the volume title, which is rightly ignored. With the
    tail rule switched off because a *head* had opened the region, the prose
    rule closed it after one page of twelve.

    Whether a fix applies is a question about where in the volume a page sits,
    not about which signal happened to name it.
    """
    pages = [_prose() for _ in range(30)]
    pages.extend(_prose() for _ in range(10))
    heads: list[str | None] = [None] * 40
    heads[30] = "Bibliographie"
    for i in range(31, 40):
        heads[i] = "LES APOLOGISTES GRECS DU IIe SIÈCLE"
    heads[0] = "LES APOLOGISTES GRECS DU IIe SIÈCLE"   # spans the volume
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[30:]] == ["bibliography"] * 10


# ── preface (spec §4.4, 0.3.0) ───────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Vorwort", "Vorwort und Dank", "Geleitwort", "Danksagung",
    "Preface", "Acknowledgements", "Préface", "Avant-propos",
    "Remerciements", "Voorwoord", "Dankwoord", "Prefazione", "Premessa",
    "Prefacio", "Agradecimientos", "Prefácio", "Предисловие",
])
def test_preface_headings_are_recognised(line):
    assert region_of_heading(line) == "preface"


def test_preface_is_not_apparatus():
    """It is named so a consumer can weigh it, never so it disappears. §4.4
    calls a wrongly excluded chapter silent loss, and a preface that leads
    into the argument is a chapter."""
    from scriptor.reflow.regions import APPARATUS
    assert "preface" in REGION_NAMES
    assert "preface" not in APPARATUS


def test_preface_does_not_swallow_prose_opening_with_the_word():
    assert region_of_heading(
        "Vorwort des Herausgebers zur dritten, vollständig neu bearbeiteten Auflage"
    ) is None


def test_format_version_is_declared_and_current():
    from scriptor.reflow.regions import FORMAT_VERSION
    assert FORMAT_VERSION == "0.3.0"
    assert "format_version: 0.3.0" in render_metadata_block()
