"""Placement of synthetic anchors and orphan flags (PREPARED_FORMAT_SPEC
§4.3): both stand at the upper bound of the interval in which the lost marker
can lie — before the next placed marker of the same page, else before the
first marker of a following page, else at the end of the paragraph."""

from scriptor.reflow.confidence import annotate_paragraph
from scriptor.reflow.core import format_paragraph_md


def fresh_state():
    return {"counter": 0, "defs": []}


def test_anchor_before_next_placed_marker_on_same_page():
    para = "[p. 5] First sentence [3] and onward [7] to the close."
    fns = {(0, 3): "third", (0, 6): "sixth, marker lost", (0, 7): "seventh"}
    occ = {0: (0, 3), 1: (0, 7)}
    state = fresh_state()
    out = format_paragraph_md(para, fns, occ, 0, state, {"5": 0})
    assert out == "[p. 5] First sentence [^1] and onward [^2][^3] to the close."
    assert state["defs"] == [
        "[^1]: third",
        "[^2]: sixth, marker lost",
        "[^3]: seventh",
    ]


def test_anchor_before_following_page_marker_when_paragraph_spans_pages():
    para = "[p. 5] The paragraph begins here [p. 6] and ends on the next page."
    fns = {(0, 4): "lost on page 5"}
    state = fresh_state()
    out = format_paragraph_md(para, fns, {}, 0, state, {"5": 0, "6": 1})
    assert (
        out == "[p. 5] The paragraph begins here [^1][p. 6] and ends on the next page."
    )


def test_anchor_falls_back_to_paragraph_end():
    para = "[p. 5] Only this text."
    fns = {(0, 4): "lost note"}
    state = fresh_state()
    out = format_paragraph_md(para, fns, {}, 0, state, {"5": 0})
    assert out == "[p. 5] Only this text. [^1]"


def test_two_anchors_share_a_bound_in_ascending_order():
    para = "[p. 5] Alpha [5] beta [8] gamma."
    fns = {(0, 5): "five", (0, 6): "six", (0, 7): "seven", (0, 8): "eight"}
    occ = {0: (0, 5), 1: (0, 8)}
    state = fresh_state()
    out = format_paragraph_md(para, fns, occ, 0, state, {"5": 0})
    assert out == "[p. 5] Alpha [^1] beta [^2] [^3][^4] gamma."
    assert state["defs"][1] == "[^2]: six"
    assert state["defs"][2] == "[^3]: seven"


def test_orphan_flag_before_upper_marker():
    para = "Text [5] with no candidate in the gap [7] end."
    fns = {5: "five", 6: "six", 7: "seven"}
    out, anns = annotate_paragraph(para, fns)
    assert len(anns) == 1 and anns[0].confidence_class == "orphan"
    assert "[?FN:6][7]" in out
