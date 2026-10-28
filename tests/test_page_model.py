import pytest

from scriptor.page import SCHEMA_VERSION, Box, Glyph, Line, Span, SourcePage, dumps, loads


def test_line_text_joins_spans_without_separator():
    line = Line(spans=[Span("Bene"), Span("dig")])
    assert line.text == "Benedig"


def test_line_size_is_the_dominant_size_by_character_count():
    line = Line(spans=[Span("aaaaaaaa", size=9.0), Span("bb", size=7.5)])
    assert line.size == 9.0


def test_line_size_is_none_without_measurements():
    assert Line(spans=[Span("plain text")]).size is None


def test_page_text_joins_lines_with_newlines():
    page = SourcePage(index=1, lines=[Line(spans=[Span("alpha")]), Line(spans=[])])
    assert page.text == "alpha\n"


def test_round_trip_preserves_the_page():
    page = SourcePage(
        index=286,
        source="pymupdf",
        width=595.0,
        height=842.0,
        lines=[
            Line(
                spans=[Span("wurden; ich habe alles bewirkt",
                            box=Box(60.0, 70.4, 295.3, 82.0), size=9.0, italic=True)],
                box=Box(60.0, 70.4, 295.3, 82.0),
                baseline=79.8,
            ),
            Line(spans=[]),
        ],
    )
    assert loads(dumps(page)) == page


def test_round_trip_preserves_an_optional_glyph_trail():
    page = SourcePage(
        index=1,
        lines=[Line(spans=[Span("42")],
                    glyphs=[Glyph("4", Box(1, 2, 3, 4), confidence=0.91),
                            Glyph("2", Box(3, 2, 5, 4))])],
    )
    assert loads(dumps(page)) == page


def test_absent_measurements_are_omitted_not_null():
    page = SourcePage(index=1, lines=[Line(spans=[Span("no geometry here")])])
    text = dumps(page)
    assert "null" not in text
    assert "box" not in text
    assert "baseline" not in text
    assert "size" not in text
    assert '"bold"' not in text          # False is the default, not a measurement


def test_unknown_schema_version_is_refused():
    with pytest.raises(ValueError, match="unsupported page schema version"):
        loads('{"version": 99, "index": 1, "lines": []}')


def test_schema_version_is_one():
    assert SCHEMA_VERSION == 1


def test_spaced_superscript_digits_read_as_one_note_number():
    # Goodman: an OCR layer sets "11" as two tiny digit spans with a space.
    line = Line(spans=[
        Span(text="1", box=Box(46, 494, 48, 500), size=2.9),
        Span(text=" ", box=Box(48, 494, 49, 500), size=2.9),
        Span(text="1", box=Box(49, 494, 51, 500), size=2.9),
        Span(text=" Smallwood, Jews", box=Box(51, 498, 120, 507), size=8.4),
    ])
    assert line.text == "11 Smallwood, Jews"


def test_spaced_digits_in_body_size_stay_as_they_are():
    line = Line(spans=[Span(text="1 1", box=Box(0, 0, 10, 9), size=8.4),
                       Span(text=" if", box=Box(10, 0, 20, 9), size=8.4)])
    assert line.text == "1 1 if"
