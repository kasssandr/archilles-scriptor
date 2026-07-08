"""Tests for running-element removal.

Focus: when removing a recurring running head, a page number embedded in it
("146 WILHELM HEIL") must be preserved, so downstream page-number detection
(parse_page) still sees it. Previously the whole line including the number
was deleted (Braunfels case, open follow-ups #1).
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
    # A number in the middle is not a page number.
    assert _extract_edge_page_number("BAND 2 STAUFER") is None


# --- strip_running_elements: header with an embedded page number ---------------

# Content-wise clearly distinct sentences: body lines must not resemble each
# other (SequenceMatcher ≥ 0.85 would otherwise group them as a running element).
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
    # Body differs in content per page, so only the running head is
    # recognised as the recurring running element.
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
        assert "WILHELM HEIL" not in page  # title gone
        assert page.strip().splitlines()[0].strip() == str(n)  # number stays


def test_strip_preserves_trailing_page_number():
    nums = (147, 149, 151)
    cleaned, headers, _ = strip_running_elements(_heil_pages(nums, trailing=True))
    assert headers
    for n, page in zip(nums, cleaned):
        assert "WILHELM HEIL" not in page
        assert page.strip().splitlines()[0].strip() == str(n)


def test_header_without_number_fully_removed():
    # Regression: a header without a number is still removed completely,
    # and no number is invented; the body is preserved.
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
        assert page.strip()  # body survives


# --- End-to-end: strip -> parse_page recovers the top page number --------------

def test_strip_then_parse_recovers_top_label():
    nums = (146, 148, 150)
    cleaned, *_ = strip_running_elements(_heil_pages(nums))
    pg = parse_page(cleaned[0])
    assert pg.label_top == "146"
    assert pg.label_bottom is None


# --- Footer with an embedded page number (consistency) -------------------------

def test_strip_preserves_footer_number():
    nums = tuple(range(10, 16))
    # The footer sits after several content-distinct body lines, so it isn't
    # already recognised as a header within the first 3 lines.
    pages = []
    for i, n in enumerate(nums):
        body = "\n".join(_DISTINCT[(2 * i + k) % len(_DISTINCT)] for k in range(4))
        pages.append(f"{body}\nQUELLENBAND ZWEI {n}")
    cleaned, _, footers = strip_running_elements(pages, footer_min=3)
    assert footers, "wiederkehrender Fußtitel muss erkannt werden"
    for n, page in zip(nums, cleaned):
        assert "QUELLENBAND" not in page
        assert page.strip().splitlines()[-1].strip() == str(n)
