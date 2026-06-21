from scriptor.reflow.core import Page
from scriptor.reflow.toc import is_toc_page, parse_toc, TOC_LINK_THRESHOLD


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
