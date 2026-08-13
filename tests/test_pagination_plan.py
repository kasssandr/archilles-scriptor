"""The pagination plan: a volume's numbering, written as a few segments.

The plan reasons in ordinals and emits strings. Those are different questions
and the tests keep them apart: ``value_at`` says what the plan predicts (used to
score a witness against it), ``label_of`` says what the page would carry.
"""

from scriptor.reflow.pagination.plan import PaginationPlan, Segment


def _plan(*segments):
    return PaginationPlan(segments=tuple(segments))


def test_a_segment_counts_upwards_from_its_start():
    plan = _plan(Segment(start_pos=1, start_label="11", style="arabic"))
    assert [plan.value_at(p) for p in (1, 2, 3)] == [11, 12, 13]
    assert [plan.label_of(p) for p in (1, 2, 3)] == ["11", "12", "13"]


def test_a_later_segment_takes_over_at_its_start():
    plan = _plan(
        Segment(start_pos=1, start_label="1", style="roman-lower"),
        Segment(start_pos=4, start_label="1", style="arabic"),
    )
    assert plan.value_at(3) == 3
    assert plan.value_at(4) == 1
    assert plan.label_of(4) == "1"


def test_positions_before_the_first_segment_have_no_label():
    plan = _plan(Segment(start_pos=5, start_label="1", style="arabic"))
    assert plan.value_at(4) is None
    assert plan.label_of(4) is None


def test_an_uncounted_segment_yields_nothing():
    plan = _plan(Segment(start_pos=1, start_label="1", style="arabic",
                         kind="uncounted"))
    assert plan.value_at(2) is None
    assert plan.label_of(2) is None


def test_a_roman_segment_predicts_a_value_but_emits_no_label():
    # The roman stretch is the front matter, where an unprinted page is as
    # likely to be uncounted as counted, and no corpus volume shows an interior
    # roman gap to verify a rule against. So roman positions are scored (the
    # witness "vii" must be able to confirm the plan) but not written back.
    plan = _plan(Segment(start_pos=1, start_label="7", style="roman-lower"))
    assert plan.value_at(3) == 9
    assert plan.label_of(3) is None


def test_an_observation_carries_its_reason():
    from scriptor.reflow.pagination.observation import Observation

    obs = Observation(pos=3, label="13", source="printed-bottom",
                      weight=1.0, why="last line of the page")
    assert obs.pos == 3 and obs.weight == 1.0
