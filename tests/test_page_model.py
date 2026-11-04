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


# Fried, Donation of Constantine p. 19: "produced between 1120 and 1150" with
# note 46 raised behind the year -- the measured spans and baseline.
def _fried_line(note: str = "46") -> Line:
    return Line(
        spans=[
            Span("produced between 1120 and 1150", box=Box(79.43, 92.97, 222.35, 103.47), size=10.5),
            Span(note, box=Box(222.29, 90.61, 229.34, 97.63), size=7.02),
            Span(". But this was soon felt", box=Box(229.37, 92.97, 427.94, 103.47), size=10.5),
        ],
        box=Box(79.43, 90.61, 427.94, 103.47),
        baseline=100.88,
    )


def test_a_note_number_raised_behind_a_year_is_set_apart():
    from scriptor.page import RAISED
    assert _fried_line().text == f"produced between 1120 and 1150{RAISED}46. But this was soon felt"


def test_the_set_apart_number_is_found_as_a_glued_marker():
    from scriptor.reflow.footnotes import substitute_markers
    (out,) = substitute_markers([_fried_line().text], {46: "note"})
    assert "1150" in out and out.endswith("[46]. But this was soon felt")


def test_digits_on_the_baseline_behind_a_number_stay_one_number():
    # Same size, same baseline: a year is a year ("August 754", Zuckerman).
    line = Line(
        spans=[Span("August 75", box=Box(10, 92.97, 60, 103.47), size=10.5),
               Span("4", box=Box(60, 92.97, 66, 103.47), size=10.5)],
        baseline=100.88,
    )
    assert line.text == "August 754"


def test_a_raised_number_behind_a_word_needs_no_mark():
    line = Line(
        spans=[Span("the Donations", box=Box(10, 92.97, 80, 103.47), size=10.5),
               Span("8", box=Box(80, 90.61, 84, 97.63), size=7.02)],
        baseline=100.88,
    )
    assert line.text == "the Donations8"
