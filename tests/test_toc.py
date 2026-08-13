from scriptor.reflow.core import Page
from scriptor.reflow.toc import is_toc_page, parse_toc, TOC_LINK_THRESHOLD, render_toc, inject_page_anchors


def _toc_page():
    return Page(-1, [
        "Einleitung .................. 9",
        "Die Krise .................. 15",
        "Der Wandel ................. 42",
        "Schluss .................... 88",
        "Anhang ..................... 95",
    ], {})


def test_is_toc_page_true_for_clean_toc():
    assert is_toc_page(_toc_page()) is True


def test_is_toc_page_false_for_prose():
    prose = Page(-1, [
        "Dies ist ein ganz normaler Fliesstextabsatz ohne Seitenzahlen.",
        "Er laeuft ueber mehrere Zeilen und endet nie auf einer Ziffer.",
        "Auch die dritte Zeile traegt keinerlei abschliessende Zahl.",
        "Die vierte Zeile ebenso wenig, sie endet auf einem Wort.",
        "Und die fuenfte schliesst den Gedanken mit einem Punkt ab.",
    ], {})
    assert is_toc_page(prose) is False


def test_is_toc_page_false_for_too_few_entries():
    short = Page(-1, ["Einleitung .... 9", "Schluss .... 88"], {})
    assert is_toc_page(short) is False


def test_parse_toc_clean_high_confidence():
    pages = [Page(-1, [
        "Einleitung .................. 9",
        "Die Krise .................. 15",
        "Der Wandel ................. 42",
        "Schluss .................... 88",
    ], {})]
    res = parse_toc(pages)
    assert res.confidence >= TOC_LINK_THRESHOLD
    assert [(e.title, e.page) for e in res.entries] == [
        ("Einleitung", 9), ("Die Krise", 15),
        ("Der Wandel", 42), ("Schluss", 88),
    ]


def test_parse_toc_hierarchy_from_numbering():
    pages = [Page(-1, [
        "1. Die Krise ............... 15",
        "1.1 Vorgeschichte .......... 18",
        "2. Der Wandel .............. 42",
    ], {})]
    res = parse_toc(pages)
    assert [(e.title, e.level) for e in res.entries] == [
        ("Die Krise", 1), ("Vorgeschichte", 2), ("Der Wandel", 1),
    ]


def test_parse_toc_roman_hierarchy_top_level():
    pages = [Page(-1, [
        "I. Einleitung ............... 9",
        "II. Der Hauptteil .......... 25",
        "III. Schluss ............... 88",
    ], {})]
    res = parse_toc(pages)
    assert [(e.title, e.level) for e in res.entries] == [
        ("Einleitung", 1), ("Der Hauptteil", 1), ("Schluss", 1),
    ]


def test_parse_toc_roman_over_arabic_nesting():
    pages = [Page(-1, [
        "I. Erster Teil ............. 9",
        "II. Zweiter Teil .......... 25",
        "1. Das Kapitel ............ 30",
        "2. Noch ein Kapitel ....... 40",
        "2.1 Ein Unterpunkt ........ 44",
        "III. Schluss .............. 88",
    ], {})]
    res = parse_toc(pages)
    assert [(e.title, e.level) for e in res.entries] == [
        ("Erster Teil", 1),
        ("Zweiter Teil", 1),
        ("Das Kapitel", 2),
        ("Noch ein Kapitel", 2),
        ("Ein Unterpunkt", 3),
        ("Schluss", 1),
    ]


def test_parse_toc_single_roman_initial_no_offset():
    # A single roman-looking entry (initial "M.") is not an outline
    # scheme -> no offset, no number splitting.
    pages = [Page(-1, [
        "M. Weber zum Geleit ....... 5",
        "1. Die Krise .............. 15",
        "2. Der Wandel ............. 42",
    ], {})]
    res = parse_toc(pages)
    assert [(e.title, e.level) for e in res.entries] == [
        ("M. Weber zum Geleit", 1), ("Die Krise", 1), ("Der Wandel", 1),
    ]


def test_parse_toc_shredded_low_confidence():
    # Baynes-like: title block and number block are physically separated.
    pages = [Page(-1, [
        "1. The History of the Byzantine Empire: an",
        "Outline",
        "II. The Economic Life of the Byzantine Empire",
        "III. Public Finances",
        "IV. The Byzantine Church",
        "33",
        "51",
        "71",
        "86",
        "136",
    ], {})]
    res = parse_toc(pages)
    assert res.confidence < TOC_LINK_THRESHOLD


_VERBATIM_MARKER = "[Table of contents preserved verbatim"


def test_render_toc_clean_produces_linked_hierarchy():
    pages = [Page(-1, [
        "1. Die Krise ............... 15",
        "1.1 Vorgeschichte .......... 18",
        "2. Der Wandel .............. 42",
    ], {})]
    res = render_toc(pages, available_pages={"15", "18", "42"})
    text = "\n".join(res.blocks)
    assert "## Contents" in text   # no heading printed -> tool fallback
    assert "- [Die Krise](#p-15) — p. 15" in text
    assert "  - [Vorgeschichte](#p-18) — p. 18" in text
    assert "- [Der Wandel](#p-42) — p. 42" in text
    assert res.anchor_targets == {"15", "18", "42"}


def test_render_toc_roman_over_arabic_indentation():
    pages = [Page(-1, [
        "I. Erster Teil ............. 9",
        "II. Zweiter Teil .......... 25",
        "1. Das Kapitel ............ 30",
    ], {})]
    res = render_toc(pages, available_pages={"9", "25", "30"})
    text = "\n".join(res.blocks)
    assert "- [Erster Teil](#p-9) — p. 9" in text
    assert "- [Zweiter Teil](#p-25) — p. 25" in text
    assert "  - [Das Kapitel](#p-30) — p. 30" in text


def test_render_toc_entry_without_body_page_has_no_link():
    pages = [Page(-1, [
        "Da ............. 15",
        "Dort ........... 42",
        "Fehlt .......... 77",
        "Ende ........... 88",
    ], {})]
    res = render_toc(pages, available_pages={"15", "42", "88"})  # 77 is missing
    text = "\n".join(res.blocks)
    assert "- [Fehlt](#p-77)" not in text
    assert "- Fehlt — p. 77" in text
    assert "77" not in res.anchor_targets


def test_render_toc_shredded_falls_back_verbatim():
    pages = [Page(-1, [
        "1. The History of the Byzantine Empire: an",
        "Outline",
        "II. The Economic Life",
        "III. Public Finances",
        "IV. The Byzantine Church",
        "33", "51", "71", "86", "136",
    ], {})]
    res = render_toc(pages, available_pages=set())
    assert res.blocks[0].startswith(_VERBATIM_MARKER)
    assert any("Outline" in b for b in res.blocks)   # original lines preserved
    assert res.anchor_targets == set()


def test_inject_anchors_first_occurrence_only():
    doc = "Foo [p. 15] bar baz [p. 15] qux"
    out = inject_page_anchors(doc, {"15"})
    assert out == "Foo [p. 15]{#p-15} bar baz [p. 15] qux"


def test_inject_anchors_only_targets():
    doc = "a [p. 15] b [p. 99] c"
    out = inject_page_anchors(doc, {"15"})
    assert out == "a [p. 15]{#p-15} b [p. 99] c"


def test_inject_anchors_missing_marker_is_noop():
    doc = "a [p. 15] b"
    out = inject_page_anchors(doc, {"77"})
    assert out == doc


from scriptor.reflow.core import assign_modes, render_book


def test_heading_trigger_multilingual_contents():
    pages = [
        Page(-1, ["CONTENTS", "Intro .... 1", "Kap 1 .... 9"], {}),
        Page(1, ["Dies ist Fliesstext " * 6 for _ in range(8)], {}),
    ]
    assign_modes(pages)
    assert pages[0].mode == "toc"


def test_assign_modes_structural_toc_in_frontmatter():
    pages = [
        Page(-1, ["Titelei", "Verlag"], {}),
        Page(-1, [
            "Einleitung ......... 9",
            "Die Krise .......... 15",
            "Der Wandel ......... 42",
            "Schluss ............ 88",
        ], {}),
        Page(1, ["Echter Fliesstext laeuft hier weiter. " * 4 for _ in range(8)], {}),
    ]
    assign_modes(pages)
    assert pages[1].mode == "toc"


# --- the two ways a table of contents was lost (nl_eerste) --------------------

def _prose_page(label=None):
    return Page(-1, ["Echter Fliesstext laeuft hier ueber die ganze Zeile. " * 2
                     for _ in range(8)], {}, label=label)


def _volume_around(*front):
    """A volume long enough that the opening tenth is a real bound, not the
    floor of ``max(1, ...)``."""
    return list(front) + [_prose_page() for _ in range(40)]


def test_a_dutch_contents_heading_is_a_trigger():
    """De eerste minister: the outline confirms the title "Inhoud" and
    ``assign_modes`` does check ``page.heading`` -- but its own trigger list
    knew no Dutch, while the region vocabulary has known `inhoud` for two
    rounds of language work. Two vocabularies for one question, and only one
    of them was maintained.
    """
    toc = Page(-1, ["9", "Oldenbarnevelt, De Witt en Fagel  13",
                    "Raad en pensionaris  15", "Werkwijze  17"], {})
    toc.heading = "Inhoud"
    pages = _volume_around(_prose_page(), toc)
    assign_modes(pages)
    assert pages[1].mode == "toc"


def test_a_contents_behind_a_prose_imprint_page_is_still_found():
    """The structural reading works on this volume -- every line of both pages
    ends in a page number -- but it was only ever asked while the mode still
    said `frontmatter`, and the imprint page had already ended that: its
    picture credits are set as running text and measure as prose.

    Position answers what the mode cannot: a register also ends its lines in
    numbers, but no register stands in the opening tenth of a volume.
    """
    imprint = Page(-1, ["Deze studie is mede tot stand gekomen door de Promotiebeurs "
                        "voor leraren van NWO en een bijdrage van Open Access."] * 8, {})
    toc = Page(-1, ["Inleiding  9", "Raad en pensionaris  15",
                    "Werkwijze  17", "Bronnen  20", "Opzet van het boek  23"], {})
    pages = _volume_around(Page(-1, ["De eerste minister van de Republiek"], {}),
                           imprint, toc)
    assign_modes(pages)
    assert pages[1].mode == "main", "die Impressum-Seite misst als Fliesstext"
    assert pages[2].mode == "toc"


def test_an_index_at_the_end_is_not_read_as_a_contents():
    """The bound is what makes the rule above safe, so it is held here: an
    index ends its lines in page numbers exactly as a table of contents does,
    and it is only the position that tells them apart.
    """
    index = Page(-1, ["Oldenbarnevelt, Johan van  45", "Witt, Johan de  78",
                      "Fagel, Gaspar  120", "Willem III  166"], {})
    pages = _volume_around(Page(-1, ["Titelei"], {}))
    pages.append(index)
    assign_modes(pages)
    assert pages[-1].mode != "toc"


def test_render_book_links_and_anchors_end_to_end():
    toc = Page(-1, [
        "Die Krise .................. 15",
        "Der Wandel ................. 42",
    ], {}, mode="toc")
    p15 = Page(15, ["Hier beginnt das Kapitel ueber die grosse Krise des Reiches."], {}, mode="main")
    p42 = Page(42, ["Und hier folgt der lange erwartete Wandel der Verhaeltnisse."], {}, mode="main")
    doc, _ = render_book([toc, p15, p42], threshold=40, fmt="md")
    assert "- [Die Krise](#p-15) — p. 15" in doc
    assert "[p. 15]{#p-15}" in doc
    assert "[p. 42]{#p-42}" in doc


# --- printed heading vs. tool fallback ----------------------------------------

def _toc_lines_page(*lines):
    return [Page(-1, list(lines), {})]


def test_printed_heading_is_carried_over_verbatim():
    """The book prints its own TOC heading. Preserve it, do not invent one —
    the same rule that keeps a printed page label roman."""
    pages = _toc_lines_page(
        "INHALT",
        "Erstes Kapitel ..... 9",
        "Zweites Kapitel .... 25",
        "Drittes Kapitel .... 30",
        "Viertes Kapitel .... 44",
    )
    res = render_toc(pages, available_pages={"9", "25", "30", "44"})
    assert res.blocks[0] == "## INHALT"


def test_printed_english_heading_is_not_germanised():
    pages = _toc_lines_page(
        "CONTENTS",
        "Introduction ....... 9",
        "The Crisis ......... 25",
        "The Turn ........... 30",
        "Aftermath .......... 44",
    )
    res = render_toc(pages, available_pages={"9", "25", "30", "44"})
    assert res.blocks[0] == "## CONTENTS"
    assert "Inhalt" not in "\n".join(res.blocks)


def test_missing_heading_falls_back_to_tool_voice():
    pages = _toc_lines_page(
        "Erstes Kapitel ..... 9",
        "Zweites Kapitel .... 25",
        "Drittes Kapitel .... 30",
    )
    res = render_toc(pages, available_pages={"9", "25", "30"})
    assert res.blocks[0] == "## Contents"


def test_long_first_line_is_not_mistaken_for_a_heading():
    pages = _toc_lines_page(
        "Ein langer Satz, der ganz sicher keine Ueberschrift eines Verzeichnisses ist",
        "Erstes Kapitel ..... 9",
        "Zweites Kapitel .... 25",
        "Drittes Kapitel .... 30",
    )
    res = render_toc(pages, available_pages={"9", "25", "30"})
    assert res.blocks[0] == "## Contents"


def test_toc_lines_use_tool_voice_for_the_page_reference():
    pages = _toc_lines_page(
        "Da ......... 15",
        "Dort ....... 42",
        "Fehlt ...... 77",
        "Ende ....... 88",
    )
    res = render_toc(pages, available_pages={"15", "42", "88"})
    text = "\n".join(res.blocks)
    assert "- [Da](#p-15) — p. 15" in text
    assert "- Fehlt — p. 77" in text     # unlinked entry keeps the reference
    assert " S. " not in text            # no German abbreviation in tool prose
