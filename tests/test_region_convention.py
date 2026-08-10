"""Region convention of PREPARED_FORMAT_SPEC §4.4.

Two things are tested apart, because the spec keeps them apart: what a region
is *called* (the vocabulary, consumer-facing) and where it *ends* (the closing
rule, which is what keeps a false positive from swallowing a book).
"""
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
    assert region_of_heading("Vorwort") is None


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
    the pages under it belong to a structure that is not apparatus.
    """
    pages = [_prose() for _ in range(30)]
    pages.append(_entries("APPENDIX", "[I] Edward rex. Ubi Harold dux"))
    pages.extend(_prose() for _ in range(9))
    heads = ["Anglo-Norman Studies XXIII"] * 40
    assign_modes(pages)
    assign_regions(pages, page_headers=heads)
    assert [p.region for p in pages[-9:]] == ["main"] * 9


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
