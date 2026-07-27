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


def test_misanchored_when_anchor_on_wrong_page():
    bad = OUTPUT.replace("at its end. [^2]", "at its end.").replace(
        "carries a note [^1]", "carries a note [^1] [^2]")
    res = evaluate_anchors(TRUTH, parse_prepared(bad))
    by_num = {(o.truth.page, o.truth.num): o.status for o in res.outcomes}
    assert by_num[("2", 1)] == "misanchored"
