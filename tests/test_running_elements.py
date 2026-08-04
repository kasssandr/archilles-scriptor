"""Tests for running-element removal.

Focus: when removing a recurring running head, a page number embedded in it
("146 WILHELM HEIL") must be preserved, so downstream page-number detection
(parse_page) still sees it. Previously the whole line including the number
was deleted (Braunfels case, open follow-ups #1).
"""

from scriptor.reflow.running_elements import (
    strip_running_elements,
    detect_running_footers,
    remove_running_footers_from_blocks,
    remove_running_headers,
    detect_running_headers,
    _extract_edge_page_number,
    _strings_are_similar,
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


# --- A running element quoted inside a longer real line ------------------------

# Regression (EXCITE 35056, p. 4): the publisher's name is the running footer,
# and a footnote cites that same publisher. The note line contains the footer
# verbatim but is much longer — it is body text, not a running element, and
# must survive. Silent loss of a text line is worse than a visible error.
_DIE_FOOTER = "Deutsches Institut für Entwicklungspolitik"
_DIE_NOTE = (
    "Bonn: Deutsches Institut für Entwicklungspolitik (Discussion Paper 7/2006)."
)


def test_similarity_rejects_a_short_substring_of_a_long_line():
    # The footer covers barely half the note line; SequenceMatcher puts them at
    # 0.72, well under the 0.85 threshold. Only the substring shortcut said yes.
    assert not _strings_are_similar(_DIE_NOTE, _DIE_FOOTER)


def test_similarity_still_accepts_a_line_that_is_essentially_the_element():
    # The shortcut's legitimate case must keep working: trailing punctuation or
    # a stray word around an otherwise identical running element.
    assert _strings_are_similar(_DIE_FOOTER + ".", _DIE_FOOTER)


def test_footer_quoted_in_a_footnote_survives():
    # Ordered as in the source: the citing note sits on an early page, the
    # plain running footer carries the rest of the volume.
    tail = "\n".join(_DISTINCT[k] for k in range(3))
    pages = [f"{tail}\n{_DIE_NOTE}"]
    for i in range(1, 7):
        body = "\n".join(_DISTINCT[(2 * i + k) % len(_DISTINCT)] for k in range(3))
        pages.append(f"{body}\n{_DIE_FOOTER}")

    cleaned, _, footers = strip_running_elements(pages, footer_min=3)
    assert footers, "wiederkehrender Fußtitel muss erkannt werden"
    for page in cleaned[1:]:
        assert _DIE_FOOTER not in page  # the real running footer goes
    assert _DIE_NOTE in cleaned[0]  # the footnote citing it stays


# --- the footer inside a cut apparatus ----------------------------------------
# Where the page geometry cut a footnote block, the running footer no longer
# sits at the foot of the body: it sits in the last line of the block, together
# with the folio. SSOAR 35056 is the case -- "36    Deutsches Institut für
# Entwicklungspolitik" -- and there the detector saw the line on too few pages
# to recognise it at all, while the block carried it straight into the notes.

def _split_pages(n=4):
    """n pages, each already divided into body text and a cut apparatus.

    Every line differs from every other, notes included: text that merely
    varies a number ("1 Vgl. Beleg 1." against "2 Vgl. Beleg 2.") is grouped
    as one recurring element and would be detected as the footer itself.
    """
    bodies, blocks = [], []
    for i in range(n):
        bodies.append(f"{_DISTINCT[2 * i]}\n{_DISTINCT[2 * i + 1]}")
        blocks.append([f"{i + 1} {_DISTINCT[2 * n + i]}", f"{i + 10}    {_DIE_FOOTER}"])
    return bodies, blocks


def test_footer_hidden_in_the_apparatus_is_detected():
    bodies, blocks = _split_pages()
    assert not detect_running_footers(bodies, min_occurrences=3), (
        "ohne die Blöcke steht der Fußtitel auf keiner Seite am Fuß des Textes"
    )
    _, _, footers = strip_running_elements(bodies, footer_min=3, foot_blocks=blocks)
    assert any(_strings_are_similar(f, _DIE_FOOTER) for f in footers)


def test_footer_leaves_the_apparatus_and_hands_back_its_folio():
    bodies, blocks = _split_pages()
    _, _, footers = strip_running_elements(bodies, footer_min=3, foot_blocks=blocks)
    cleaned, rescued = remove_running_footers_from_blocks(blocks, footers)
    assert cleaned[0] == [f"1 {_DISTINCT[8]}"], "der Fußtitel gehört nicht zu Note 1"
    assert rescued[0] == "10", "die Folio darf nicht mit dem Fußtitel verschwinden"


def test_a_block_without_the_footer_is_left_alone():
    blocks = [["1 Vgl. Beleg 1.", "und eine Fortsetzungszeile dazu."]]
    cleaned, rescued = remove_running_footers_from_blocks(blocks, [_DIE_FOOTER])
    assert cleaned[0] == blocks[0]
    assert rescued[0] is None
