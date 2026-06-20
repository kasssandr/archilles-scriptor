"""Tests für die Running-Element-Entfernung.

Schwerpunkt: Beim Entfernen eines wiederkehrenden Kolumnentitels muss eine
darin eingebettete Seitenzahl ("146 WILHELM HEIL") erhalten bleiben, damit die
nachgelagerte Seitenzahl-Erkennung (parse_page) sie weiterhin sieht. Vorher
wurde die ganze Zeile inkl. Zahl gelöscht (Braunfels-Fall, offene-nacharbeiten #1).
"""

from scriptor.reflow.running_elements import (
    strip_running_elements,
    remove_running_headers,
    detect_running_headers,
    _extract_edge_page_number,
)
from scriptor.reflow.core import parse_page


# --- _extract_edge_page_number ------------------------------------------------

def test_extract_leading_edge_number():
    assert _extract_edge_page_number("146 WILHELM HEIL") == "146"


def test_extract_trailing_edge_number():
    assert _extract_edge_page_number("WILHELM HEIL 147") == "147"


def test_extract_none_without_edge_number():
    assert _extract_edge_page_number("WILHELM HEIL") is None
    # Eine Zahl in der Mitte ist keine Seitenzahl.
    assert _extract_edge_page_number("BAND 2 STAUFER") is None


# --- strip_running_elements: Header mit eingebetteter Seitenzahl ---------------

# Inhaltlich klar verschiedene Sätze: Body-Zeilen dürfen einander nicht
# ähneln (SequenceMatcher ≥ 0,85 würde sie sonst als Running-Element gruppieren).
_DISTINCT = [
    "Karl der Große gründete viele Klöster im fränkischen Reich.",
    "Die Reichenau war ein Zentrum mittelalterlicher Buchmalerei.",
    "Benedikt von Aniane reformierte das abendländische Mönchtum.",
    "Ludwig der Fromme förderte die klösterliche Erneuerung sehr.",
    "Skriptorien kopierten kostbare Handschriften über viele Jahre.",
    "Die Abtei Gellone pflegte eine besondere liturgische Tradition.",
    "Pippin stärkte das Bündnis mit dem römischen Papsttum deutlich.",
    "Alkuin von York prägte die karolingische Bildungsreform stark.",
    "Mönche bewahrten antikes Wissen in stillen Bibliotheken auf.",
    "Urkunden regelten Besitz und Rechte der Klöster ganz genau.",
    "Die Hofschule zu Aachen versammelte die Gelehrten der Epoche.",
    "Reliquien zogen zahlreiche Pilger in fränkische Heiligtümer.",
]


def _heil_pages(nums, *, trailing=False):
    # Body je Seite inhaltlich verschieden, damit nur der Kolumnentitel als
    # wiederkehrendes Running-Element erkannt wird.
    pages = []
    for i, n in enumerate(nums):
        b1 = _DISTINCT[(2 * i) % len(_DISTINCT)]
        b2 = _DISTINCT[(2 * i + 1) % len(_DISTINCT)]
        head = f"WILHELM HEIL {n}" if trailing else f"{n} WILHELM HEIL"
        pages.append(f"{head}\n{b1}\n{b2}")
    return pages


def test_strip_preserves_leading_page_number():
    nums = (146, 148, 150, 152)
    cleaned, headers, _ = strip_running_elements(_heil_pages(nums))
    assert headers, "wiederkehrender Kolumnentitel muss erkannt werden"
    for n, page in zip(nums, cleaned):
        assert "WILHELM HEIL" not in page  # Titel weg
        assert page.strip().splitlines()[0].strip() == str(n)  # Zahl bleibt


def test_strip_preserves_trailing_page_number():
    nums = (147, 149, 151)
    cleaned, headers, _ = strip_running_elements(_heil_pages(nums, trailing=True))
    assert headers
    for n, page in zip(nums, cleaned):
        assert "WILHELM HEIL" not in page
        assert page.strip().splitlines()[0].strip() == str(n)


def test_header_without_number_fully_removed():
    # Regression: Header ohne Zahl wird weiterhin komplett entfernt,
    # und es wird keine Zahl erfunden; der Body bleibt erhalten.
    nums = (1, 2, 3, 4)
    pages = []
    for i in nums:
        b1 = _DISTINCT[(2 * (i - 1)) % len(_DISTINCT)]
        b2 = _DISTINCT[(2 * (i - 1) + 1) % len(_DISTINCT)]
        pages.append(f"WILHELM HEIL\n{b1}\n{b2}")
    cleaned, headers, _ = strip_running_elements(pages)
    assert headers
    for page in cleaned:
        assert "WILHELM HEIL" not in page
        assert not any(c.isdigit() for c in page)
        assert page.strip()  # Body überlebt


# --- Ende-zu-Ende: strip -> parse_page findet die Top-Seitenzahl --------------

def test_strip_then_parse_recovers_top_number():
    nums = (146, 148, 150)
    cleaned, *_ = strip_running_elements(_heil_pages(nums))
    pg = parse_page(cleaned[0])
    assert pg.num_top == 146
    assert pg.num_bottom == -1


# --- Footer mit eingebetteter Seitenzahl (Konsistenz) -------------------------

def test_strip_preserves_footer_number():
    nums = tuple(range(10, 16))
    # Footer steht hinter mehreren inhaltlich verschiedenen Body-Zeilen, damit
    # er nicht bereits in den ersten 3 Zeilen als Header erkannt wird.
    pages = []
    for i, n in enumerate(nums):
        body = "\n".join(_DISTINCT[(2 * i + k) % len(_DISTINCT)] for k in range(4))
        pages.append(f"{body}\nQUELLENBAND ZWEI {n}")
    cleaned, _, footers = strip_running_elements(pages, footer_min=3)
    assert footers, "wiederkehrender Fußtitel muss erkannt werden"
    for n, page in zip(nums, cleaned):
        assert "QUELLENBAND" not in page
        assert page.strip().splitlines()[-1].strip() == str(n)
