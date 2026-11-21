"""One rule for a marker glued to its word (footnotes.glued_marker)."""
import re

import pytest

from scriptor.page import RAISED
from scriptor.reflow.footnotes import (
    GLUED_EXCLUSIONS,
    glued_marker,
    substitute_markers,
)

# The endnotes' rule as it stood before it moved into glued_marker.
OLD_GLUED = re.compile(
    r"(?<=[^\s\d:\-–—/\[(])(?<!\d\.)(?<!\d,)(\d{1,3})(?=$|[^\w:\-–—/\]]|:(?!\d))")

LINES = [
    "question.1 and Bibel23", 'he said"64 then', "Joh 12:9 and Wort9.",
    "(14,1,1) here.1", "S. 29-30 Beleg30", "S. 29–30, Beleg30", "Abschnitt 2.6 Aussage.6",
    "Seele2: Eine", "Ps 3:4", "see [12] and x12]", "a/5 b-5 c(5 d[5", "x5/ y5– z5]",
    "August 754", f"1150{RAISED}46. But", "end2", "Zeile7\nnext8", "x1a y2_ z3",
]


@pytest.mark.parametrize("line", LINES)
def test_default_is_the_endnotes_rule_as_it_was(line):
    old = [(m.start(1), m.group(1)) for m in OLD_GLUED.finditer(line)]
    new = [(m.start(1), m.group(1)) for m in glued_marker().finditer(line)]
    assert new == old


# The four probes of the review: the wrong number on the left used to take
# the note, the real marker on the right stayed bare.
PROBES = [
    ("(Joh 12:9) das Wort9 selbst.", 9, "Wort9"),
    ("Isidor (14,1,1) endet hier.1", 1, "hier.1"),
    ("S. 29-30 der Beleg30 dazu.", 30, "Beleg30"),
    ("Abschnitt 2.6 die Aussage.6", 6, "Aussage.6"),
]


@pytest.mark.parametrize("line,num,real", PROBES)
def test_endnotes_find_the_real_marker_in_all_four(line, num, real):
    (m,) = glued_marker([num]).finditer(line)
    assert line[:m.end()].endswith(real)


@pytest.mark.parametrize("line,num,placed", [
    ("(Joh 12:9) das Wort9 selbst.", 9, "(Joh 12:9) das Wort [9] selbst."),
    ("S. 29-30 der Beleg30 dazu.", 30, "S. 29-30 der Beleg [30] dazu."),
    ("S. 29–30 der Beleg30 dazu.", 30, "S. 29–30 der Beleg [30] dazu."),
    ("um 1198/99 gewählt99 hier", 99, "um 1198/99 gewählt [99] hier"),
])
def test_footnote_path_skips_a_digit_joined_number(line, num, placed):
    assert substitute_markers([line], {num: "note"}) == [placed]


# On the footnote path a period or comma behind a digit does not bar: in
# born-digital volumes the real marker stands there more often than a section
# number does ("in fall 312.186", Ando; "1147,380 Otto", Wolf). The cost is the
# section number and the reference the review probed, which keep their old
# reading here; the endnotes, on bare text, bar both.
@pytest.mark.parametrize("line,num,placed", [
    ("during his campaign in fall 312.6 Then", 6, "during his campaign in fall 312. [6] Then"),
    ("Domvogt (Tafel 6) 1147,8 Otto", 8, "Domvogt (Tafel 6) 1147, [8] Otto"),
    ("in the following terms:7 Our", 7, "in the following terms: [7] Our"),
    ("the ius naturale)20—they", 20, "the ius naturale) [20]—they"),
])
def test_footnote_path_keeps_markers_behind_years_and_colons(line, num, placed):
    assert substitute_markers([line], {num: "note"}) == [placed]


@pytest.mark.parametrize("line,num,placed", [
    ("the question.1 stays", 1, "the question. [1] stays"),
    ('he said"64 then', 64, 'he said" [64] then'),
    ("die Seele2: Eine", 2, "die Seele [2]: Eine"),
    (f"between 1120 and 1150{RAISED}46. But", 46, f"between 1120 and 1150{RAISED} [46]. But"),
])
def test_glued_markers_still_found(line, num, placed):
    assert substitute_markers([line], {num: "note"}) == [placed]


def test_a_year_gives_no_glued_marker():
    # Pass 1 finds nothing glued; pass 2 wants the number after a space.
    assert substitute_markers(["im August 754 starb"], {4: "n"}) == ["im August 754 starb"]


def test_numbers_limit_the_pattern():
    pat = glued_marker([3, 12])
    assert [m.group(1) for m in pat.finditer("a3 b12 c7 d123")] == ["3", "12"]


def test_each_exclusion_can_be_left_out():
    line = "(14,1,1)"
    assert not glued_marker([1]).search(line)
    assert glued_marker([1], GLUED_EXCLUSIONS - {"digit_comma"}).search(line)
    assert glued_marker([6], frozenset()).search("2.6")
    assert glued_marker([9], frozenset()).search("12:9")


def test_unknown_exclusion_is_an_error():
    with pytest.raises(ValueError):
        glued_marker(exclude=frozenset({"digit_dot"}))
