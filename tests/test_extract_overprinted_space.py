"""A word space the pen moved back over (Klawans, Josephus and the Theologies
of Ancient Judaism): written, but drawn over by the glyph after it."""

from scriptor.extract.pymupdf_backend import _open_gaps


def _span(chars, size=10.22, y=314.7):
    """A rawdict span from (char, x0, x1) triples."""
    return {"chars": [{"c": c, "bbox": (x0, y - size, x1, y)} for c, x0, x1 in chars],
            "size": size, "origin": (chars[0][1], y)}


def _text(spans):
    return "".join(s["text"] for s in _open_gaps(spans))


def test_a_raised_number_drawn_over_the_space_is_glued_to_its_word():
    # p. 20: ")" 131.79-134.95, "." -137.35, " " 137.50-140.05, "1" from 137.51.
    word = _span([(")", 131.79, 134.95), (".", 134.80, 137.35), (" ", 137.50, 140.05)])
    mark = _span([("1", 137.51, 139.24)], size=6.13, y=311.4)
    after = _span([(" ", 139.24, 141.79), ("O", 142.63, 150.22), ("n", 150.22, 155.3)])
    assert _text([word, mark, after]) == ").1 On"


def test_a_stop_and_a_ligature_drawn_over_the_space_close_up():
    # "War , ed." and "modiﬁ ed": the comma and the "e" stand on the space.
    assert _text([_span([("r", 0, 4), (" ", 4, 6.5), (",", 4.1, 6.6), (" ", 6.6, 9.1),
                         ("e", 10.5, 15)])]) == "r, e"
    assert _text([_span([("ﬁ", 0, 5.6), (" ", 5.6, 8.1), ("e", 5.6, 10.1),
                         ("d", 10.1, 15.2)])]) == "ﬁed"


def test_a_tight_word_space_stays():
    # p. 311, the tightest real space: 0.107 em between the words.
    size = 8.97
    gap = 0.107 * size
    assert _text([_span([("D", 0, 6), (".", 6, 8), (" ", 8, 8 + gap), ("S", 8 + gap, 13)],
                        size=size)]) == "D. S"


def test_the_space_after_a_raised_number_stays():
    # "33b)101 —is": glued to the dash, the marker reads as a range.
    word = _span([(")", 0, 3.4)])
    mark = _span([("1", 3.5, 6.1), ("0", 6.1, 8.7), ("1", 8.7, 11.3), (" ", 11.3, 13.8)],
                 size=6.13, y=311.4)
    dash = _span([("—", 11.3, 21.5), ("i", 21.5, 24.3)])
    assert _text([word, mark, dash]) == ")101 —i"


def test_a_space_the_next_glyph_only_overlaps_stays():
    # Ando, a tight justified line: the "T" begins 0.08 em into the space.
    size = 10.8
    assert _text([_span([("!", 0, 3), (" ", 3, 6), ("T", 3 + 0.08 * size, 10)],
                        size=size)]) == "! T"


def test_an_ocr_layer_and_a_rotated_line_are_left_alone():
    # Invisible text (alpha 0): the boxes are the OCR engine's guess.
    hidden = _span([("P", 0, 4), (" ", 4, 6.5), ("h", 4, 9)])
    hidden["alpha"] = 0
    assert _text([hidden]) == "P h"
    # A rotated table cell does not move along x at all.
    spans = [_span([("a", 0, 0), (" ", 0, 0), ("b", 0, 0)])]
    assert "".join(s["text"] for s in _open_gaps(spans, horizontal=False)) == "a b"


def test_right_to_left_script_is_left_alone():
    # Hebrew runs the other way: the glyph after the space stands left of it.
    assert _text([_span([("ב", 20, 25), (" ", 15, 17.5), ("א", 10, 15)])]) == "ב א"
