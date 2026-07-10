"""Unit tests for the extracted footnotes module (Etappe 2-A).

Locks the contract of the symbols moved out of core.py: marker substitution
(two-pass, single-consume), the footnote-definition and placed-marker regexes,
and the superscript-digit normalisation (which the reflow golden fixture does
not exercise).
"""

from scriptor.reflow.footnotes import (
    FOOTNOTE_RE,
    PLACED_MARKER_RE,
    SUPERSCRIPT_DIGITS,
    substitute_markers,
)


def test_substitute_pass1_glued_marker():
    # Digit glued to the end of a word -> placed as " [N]".
    assert substitute_markers(["Das Wort64 steht hier."], {64: "note"}) == [
        "Das Wort [64] steht hier."
    ]


def test_substitute_pass2_whitespace_separated():
    # Digit separated from the preceding token by whitespace -> "[N]".
    assert substitute_markers(['gefuehrt" 30 weiter'], {30: "note"}) == [
        'gefuehrt" [30] weiter'
    ]


def test_substitute_consumes_each_number_once():
    # Only the first occurrence of a footnote number is replaced.
    assert substitute_markers(["A1 und nochmal 1 spaeter"], {1: "note"}) == [
        "A [1] und nochmal 1 spaeter"
    ]


def test_substitute_never_matches_inside_a_number():
    # Zuckerman p. 39: "arriving in August 754" bore footnote 4 out of the
    # year's last digit, while the genuine marker "fall.4" went empty. A
    # printed marker glues to a letter or punctuation, never to another digit.
    line = "arriving in August 754, and the blockade ended with its fall.4"
    assert substitute_markers([line], {4: "note"}) == [
        "arriving in August 754, and the blockade ended with its fall. [4]"
    ]


def test_substitute_leaves_a_bare_year_alone():
    # No safe anchor at all: better an unplaced footnote (hanging reference,
    # flagged by the audit) than a marker invented inside a year.
    line = "scored an initial victory in May 755."
    assert substitute_markers([line], {5: "note"}) == [line]


def test_substitute_ignores_numbers_not_in_footnotes():
    # Empty footnote set: untouched. A non-footnote digit: untouched.
    assert substitute_markers(["im Jahr 1798 geschah es"], {}) == [
        "im Jahr 1798 geschah es"
    ]
    assert substitute_markers(["Wort5"], {3: "x"}) == ["Wort5"]


def test_footnote_def_regex_matches_numbered_line():
    m = FOOTNOTE_RE.match("12) Eine Fussnote.")
    assert m and m.group(1) == "12" and m.group(2) == "Eine Fussnote."
    assert FOOTNOTE_RE.match("kein Marker") is None


def test_placed_marker_regex_finds_bracketed_numbers():
    assert [m.group(1) for m in PLACED_MARKER_RE.finditer("a [3] b [17]")] == [
        "3",
        "17",
    ]


def test_superscript_digits_normalise_to_ascii():
    assert "x¹ y⁰⁴".translate(SUPERSCRIPT_DIGITS) == "x1 y04"
