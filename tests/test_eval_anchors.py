"""Anchor correctness: the metric that carries the benchmark. Flagged counts
as handled (never as damage); a silent wrong anchor is the expensive error."""
from scriptor.eval.adapters import parse_prepared
from scriptor.eval.anchors import evaluate_anchors
from scriptor.eval.ground_truth import loads_truth

TRUTH = loads_truth("""
volume = "t"
pages = ["1", "2"]

[[footnotes]]           # correctly anchored
page = "1"
num = 1
anchor_after = "carries a note"
definition_starts = "First note"
status = "intact"

[[footnotes]]           # flagged in the review copy
page = "1"
num = 2
anchor_after = "lost here"
definition_starts = "Second note"
status = "marker_lost"

[[footnotes]]           # anchored on the right page, position unknown
page = "2"
num = 1
definition_starts = "Third note"
status = "marker_lost"

[[footnotes]]           # will be missing from the output
page = "2"
num = 2
definition_starts = "Fourth note"
status = "intact"
""")

OUTPUT = """[p. 1] The sentence carries a note [^1] while another was lost here&[?FN:2|&] sadly.

[p. 2] Second page text with a rescued anchor at its end. [^2]

[^1]: First note text.

[^2]: Third note text.

[^3]: Second note text.
"""


def test_statuses():
    doc = parse_prepared(OUTPUT)
    res = evaluate_anchors(TRUTH, doc)
    by_num = {(o.truth.page, o.truth.num): o.status for o in res.outcomes}
    assert by_num[("1", 1)] == "anchored_exact"
    assert by_num[("1", 2)] == "flagged"
    assert by_num[("2", 1)] == "anchored_page"
    assert by_num[("2", 2)] == "lost"


def test_rates():
    res = evaluate_anchors(TRUTH, parse_prepared(OUTPUT))
    assert res.anchor_rate == 0.5           # 2 of 4
    assert res.handled_rate == 0.75         # + flagged
    assert res.silent_damage_rate == 0.25   # the lost one


TWINS = loads_truth("""
volume = "t"
pages = ["163"]

[[footnotes]]
page = "163"
num = 5
anchor_after = "hob er seine Verwandtschaft hervor"
definition_starts = "Amm. 26,6,18."
definition_ends = "Amm. 26,6,18."
status = "intact"

[[footnotes]]
page = "163"
num = 6
anchor_after = "zum Kaiser ausgerufen"
definition_starts = "Amm. 26,6,18."
definition_ends = "Amm. 26,6,18."
status = "intact"
""")

TWIN_OUTPUT = """[p. 163] Prokop hob er seine Verwandtschaft hervor [^5] und wurde am
28. September 365 zum Kaiser ausgerufen [^6] .

[^5]: Amm. 26,6,18.

[^6]: Amm. 26,6,18.
"""


def test_two_notes_printing_the_same_reference_are_told_apart_by_their_anchors():
    # Themistios p. 163 prints "Amm. 26,6,18." twice, as notes 5 and 6. No
    # snippet can separate them, so the first matching definition is the wrong
    # answer for one of the two -- the anchor has to decide which is which.
    res = evaluate_anchors(TWINS, parse_prepared(TWIN_OUTPUT))
    assert [o.status for o in res.outcomes] == ["anchored_exact", "anchored_exact"]


def test_misanchored_when_anchor_on_wrong_page():
    bad = OUTPUT.replace("at its end. [^2]", "at its end.").replace(
        "carries a note [^1]", "carries a note [^1] [^2]")
    res = evaluate_anchors(TRUTH, parse_prepared(bad))
    by_num = {(o.truth.page, o.truth.num): o.status for o in res.outcomes}
    assert by_num[("2", 1)] == "misanchored"
