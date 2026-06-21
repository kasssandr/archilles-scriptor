from scriptor.reflow.core import Page
from scriptor.reflow.toc import is_toc_page


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
