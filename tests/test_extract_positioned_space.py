"""A word space the file only moved over (Ando, Matter of the Gods)."""

from scriptor.extract.pymupdf_backend import _open_gaps


def _span(text, x, size=10.75, y=120.0, step=5.0, gaps=None):
    """A rawdict span: one glyph per char, ``gaps`` = {index: extra pt before it}."""
    chars = []
    for i, ch in enumerate(text):
        x += (gaps or {}).get(i, 0.0)
        chars.append({"c": ch, "bbox": (x, y - size, x + step, y)})
        x += step
    return {"chars": chars, "size": size, "origin": (chars[0]["bbox"][0], y)}


def _text(spans):
    return "".join(s["text"] for s in _open_gaps(spans))


def test_stop_then_capital_over_a_gap_is_a_space():
    assert _text([_span("halves.The three", 0, gaps={7: 1.56})]) == "halves. The three"


def test_justified_line_gap_counts_too():
    assert _text([_span("sway.This view", 0, gaps={5: 0.78})]) == "sway. This view"


def test_raised_number_then_word_is_a_space():
    word = _span("myths.", 0)
    mark = _span("3", 30, size=7.2, y=117.0)
    after = _span("Regardless", 36.6)
    assert _text([word, mark, after]) == "myths.3 Regardless"


def test_letter_spaced_head_and_abbreviations_stay():
    assert _text([_span("the matter", 0, gaps={1: 1.5, 2: 1.5})]) == "the matter"
    assert _text([_span("A.D. 70", 0, gaps={2: 1.5})]) == "A.D. 70"
    assert _text([_span("Ph.D. thesis", 0, gaps={3: 1.5})]) == "Ph.D. thesis"
    assert _text([_span("BL.Add.12150", 0, gaps={3: 1.5})]) == "BL.Add.12150"
    assert _text([_span("www.uni-hamburg.de", 0, gaps={4: 1.5})]) == "www.uni-hamburg.de"


def test_subscript_index_is_no_raised_number():
    base = _span("x", 0)
    sub = _span("1", 5, size=7.2, y=122.0)
    paren = _span("Ab", 12.6)
    assert _text([base, sub, paren]) == "x1Ab"
