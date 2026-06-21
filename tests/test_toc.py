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


def test_parse_toc_shredded_low_confidence():
    # Baynes-artig: Titelblock und Zahlenblock physisch getrennt.
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


_VERBATIM_MARKER = "[Inhaltsverzeichnis: verbatim erhalten"


def test_render_toc_clean_produces_linked_hierarchy():
    pages = [Page(-1, [
        "1. Die Krise ............... 15",
        "1.1 Vorgeschichte .......... 18",
        "2. Der Wandel .............. 42",
    ], {})]
    res = render_toc(pages, available_pages={15, 18, 42})
    text = "\n".join(res.blocks)
    assert "## Inhaltsverzeichnis" in text
    assert "- [Die Krise](#p-15) — S. 15" in text
    assert "  - [Vorgeschichte](#p-18) — S. 18" in text
    assert "- [Der Wandel](#p-42) — S. 42" in text
    assert res.anchor_targets == {15, 18, 42}


def test_render_toc_entry_without_body_page_has_no_link():
    pages = [Page(-1, [
        "Da ............. 15",
        "Dort ........... 42",
        "Fehlt .......... 77",
        "Ende ........... 88",
    ], {})]
    res = render_toc(pages, available_pages={15, 42, 88})  # 77 fehlt
    text = "\n".join(res.blocks)
    assert "- [Fehlt](#p-77)" not in text
    assert "- Fehlt — S. 77" in text
    assert 77 not in res.anchor_targets


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
    assert any("Outline" in b for b in res.blocks)   # Originalzeilen erhalten
    assert res.anchor_targets == set()


def test_inject_anchors_first_occurrence_only():
    doc = "Foo [S. 15] bar baz [S. 15] qux"
    out = inject_page_anchors(doc, {15})
    assert out == "Foo [S. 15]{#p-15} bar baz [S. 15] qux"


def test_inject_anchors_only_targets():
    doc = "a [S. 15] b [S. 99] c"
    out = inject_page_anchors(doc, {15})
    assert out == "a [S. 15]{#p-15} b [S. 99] c"


def test_inject_anchors_missing_marker_is_noop():
    doc = "a [S. 15] b"
    out = inject_page_anchors(doc, {77})
    assert out == doc


from scriptor.reflow.toc import detect_trailing_toc


def _prose(n=8, w=60):
    return Page(200, ["x" * w for _ in range(n)], {}, mode="main")


def _toc_like():
    return Page(300, [
        "Anhang A .......... 201",
        "Anhang B .......... 215",
        "Register .......... 240",
        "Nachwort .......... 255",
    ], {}, mode="main")


def test_detect_trailing_toc_flips_end_block():
    pages = [_prose(), _prose(), _toc_like(), _toc_like()]
    detect_trailing_toc(pages)
    assert [p.mode for p in pages] == ["main", "main", "toc", "toc"]


def test_detect_trailing_toc_stops_at_nontoc():
    pages = [_toc_like(), _prose(), _toc_like()]
    detect_trailing_toc(pages)
    # Nur der zusammenhaengende Endblock; das mittlere prose stoppt den Lauf.
    assert [p.mode for p in pages] == ["main", "main", "toc"]


def test_detect_trailing_toc_ignores_non_main():
    reg = _toc_like()
    reg.mode = "raw"
    pages = [_prose(), reg]
    detect_trailing_toc(pages)
    assert [p.mode for p in pages] == ["main", "raw"]


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


def test_render_book_links_and_anchors_end_to_end():
    toc = Page(-1, [
        "Die Krise .................. 15",
        "Der Wandel ................. 42",
    ], {}, mode="toc")
    p15 = Page(15, ["Hier beginnt das Kapitel ueber die grosse Krise des Reiches."], {}, mode="main")
    p42 = Page(42, ["Und hier folgt der lange erwartete Wandel der Verhaeltnisse."], {}, mode="main")
    doc, _ = render_book([toc, p15, p42], threshold=40, fmt="md")
    assert "- [Die Krise](#p-15) — S. 15" in doc
    assert "[S. 15]{#p-15}" in doc
    assert "[S. 42]{#p-42}" in doc
