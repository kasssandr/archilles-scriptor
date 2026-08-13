"""Scoring: which segment explains the most of what the witnesses said.

The fit knows nothing but observations, so these tests build them by hand -- no
PDF, no pages, no pipeline.
"""

import pytest

from scriptor.reflow.pagination.observation import Observation
from scriptor.reflow.pagination.plan import FitParams, best_segment, fit

P = FitParams()


def _obs(pos, label, weight=1.0, source="printed-bottom"):
    return Observation(pos=pos, label=label, source=source, weight=weight,
                       why="test")


def test_the_best_segment_is_the_offset_most_observations_agree_on():
    obs = [_obs(1, "11"), _obs(2, "12"), _obs(4, "14")]
    seg, score = best_segment(obs, 1, 6, P)
    assert seg.start_pos == 1 and seg.start_label == "11"
    assert seg.style == "arabic"
    assert score == 3.0


def test_a_single_misreading_does_not_win_against_a_run():
    # One page misread as "2020" (an imprint year) against three in sequence.
    obs = [_obs(1, "11"), _obs(2, "2020"), _obs(3, "13"), _obs(4, "14")]
    seg, score = best_segment(obs, 1, 6, P)
    assert seg.start_label == "11"
    # Three confirm, one position is left unexplained and is charged mu.
    assert score == 3.0 - P.mu * 1.0


def test_a_page_speaks_with_one_voice():
    # Both edges observe every page: a running head at the top, the folio at the
    # bottom. Counting the losing edge as a contradiction would make every page
    # cost more than it pays, and no segment could ever beat "uncounted".
    obs = [
        _obs(1, "11", source="printed-bottom"),
        _obs(1, "77", source="printed-top"),
        _obs(2, "12", source="printed-bottom"),
        _obs(2, "77", source="printed-top"),
    ]
    seg, score = best_segment(obs, 1, 4, P)
    assert seg.start_label == "11"
    assert score == 2.0


def test_the_heavier_witness_wins_a_position():
    obs = [_obs(1, "11"), _obs(1, "40", weight=0.3, source="catalogue"),
           _obs(2, "12")]
    seg, score = best_segment(obs, 1, 4, P)
    assert seg.start_label == "11" and score == 2.0


def test_a_roman_run_scores_like_an_arabic_one():
    obs = [_obs(1, "vii"), _obs(2, "viii"), _obs(3, "ix")]
    seg, score = best_segment(obs, 1, 4, P)
    assert seg.style == "roman-lower" and seg.start_label == "7"
    assert score == 3.0


def test_a_style_change_inside_the_interval_costs():
    obs = [_obs(1, "vii"), _obs(2, "viii"), _obs(3, "1")]
    seg, score = best_segment(obs, 1, 4, P)
    assert seg.style == "roman-lower"
    assert score == 2.0 - P.mu * 1.0


def test_an_interval_without_observations_has_no_counted_segment():
    seg, score = best_segment([], 1, 4, P)
    assert seg is None and score == 0.0


def test_a_segment_may_not_start_below_page_one():
    # "2" on position 17 would put value -14 at position 1. No volume counts
    # backwards past its own first page.
    seg, _ = best_segment([_obs(17, "2")], 1, 20, P)
    assert seg is None


def test_ties_go_to_the_smaller_offset():
    # Two offsets explain one observation each; the result must not depend on
    # dict ordering.
    obs = [_obs(1, "5"), _obs(3, "9")]
    seg, _ = best_segment(obs, 1, 4, P)
    assert seg.start_label == "5"


def test_declaring_an_observed_stretch_uncounted_costs():
    # A page that prints "12" is numbered. Calling it uncounted contradicts it
    # exactly as a wrong counted segment would -- otherwise "uncounted" scores
    # zero everywhere and a volume with one printed label ends up with none.
    from scriptor.reflow.pagination.plan import score_uncounted

    assert score_uncounted([_obs(1, "12")], 1, 4, P) == -P.mu
    assert score_uncounted([], 1, 4, P) == 0.0


# ----------------------------------------------------------------------
# the fit: which sequence of segments explains the volume
# ----------------------------------------------------------------------

def test_one_consistent_run_yields_one_segment():
    obs = [_obs(p, str(10 + p)) for p in range(1, 6)]
    plan = fit(obs, boundaries=[1], last_pos=5, params=P)
    assert len(plan.segments) == 1
    assert [plan.value_at(p) for p in range(1, 6)] == [11, 12, 13, 14, 15]


def test_a_script_change_becomes_a_second_segment():
    obs = [_obs(1, "vii"), _obs(2, "viii"), _obs(3, "1"), _obs(4, "2")]
    plan = fit(obs, boundaries=[1, 3], last_pos=4, params=P)
    assert len(plan.segments) == 2
    assert plan.segments[1].start_pos == 3
    assert plan.segments[1].style == "arabic"
    assert plan.value_at(4) == 2


def test_a_boundary_that_buys_nothing_is_not_taken():
    # The segment price must exceed what one observation is worth, or the fit
    # cuts the volume into pieces at every candidate.
    obs = [_obs(p, str(10 + p)) for p in range(1, 6)]
    plan = fit(obs, boundaries=[1, 3], last_pos=5, params=P)
    assert len(plan.segments) == 1


def test_a_volume_nobody_can_read_gets_an_uncounted_plan():
    plan = fit([], boundaries=[1], last_pos=5, params=P)
    assert all(s.kind == "uncounted" for s in plan.segments)
    assert plan.value_at(3) is None


def test_the_offset_may_jump_at_a_boundary():
    # Carlomagno: the PDF drops the blank before a chapter opening, so the
    # printed number runs one further than the physical page from there on.
    obs = [_obs(1, "1"), _obs(2, "2"), _obs(3, "4"), _obs(4, "5")]
    plan = fit(obs, boundaries=[1, 3], last_pos=4, params=P)
    assert len(plan.segments) == 2
    assert [plan.value_at(p) for p in range(1, 5)] == [1, 2, 4, 5]


def test_an_unreadable_stretch_between_two_runs_is_left_uncounted():
    # An uncounted plate: the numbers on either side do not meet across it.
    obs = [_obs(1, "12"), _obs(4, "14")]
    plan = fit(obs, boundaries=[1, 4], last_pos=4, params=P)
    assert [plan.value_at(p) for p in (1, 4)] == [12, 14]


def test_the_fit_stays_fast_on_a_whole_volume():
    # The largest corpus volume has 371 pages. The work is quadratic in the
    # number of boundary candidates, which is why the candidate list is kept
    # deliberately short.
    import time

    # A boundary per page is the worst a volume can propose. Scoring each
    # candidate offset separately took 12 seconds at 200 boundaries; carrying
    # the tally forward brings the same case to a fifth of a second.
    obs = [_obs(p, str(p)) for p in range(1, 401)]
    bounds = list(range(1, 401))
    t0 = time.perf_counter()
    plan = fit(obs, boundaries=bounds, last_pos=400, params=P)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"fit took {elapsed:.2f}s"
    assert len(plan.segments) == 1


def test_the_fast_tally_agrees_with_the_plain_definition():
    """score_segment states what a score *is*; the tally computes it quickly.

    The speed comes from an algebraic identity, not from a different rule, so
    the two have to agree exactly -- including on the awkward inputs: two edges
    at odds, a witness of lesser weight, a numbering change mid-stretch.
    """
    from scriptor.reflow.pagination.plan import score_segment, score_uncounted

    cases = [
        [_obs(1, "11"), _obs(2, "12"), _obs(4, "14")],
        [_obs(1, "11"), _obs(1, "77", source="printed-top"), _obs(2, "12")],
        [_obs(1, "11"), _obs(1, "40", weight=0.3, source="catalogue")],
        [_obs(1, "vii"), _obs(2, "viii"), _obs(3, "1"), _obs(4, "2")],
        [_obs(1, "2020"), _obs(2, "12"), _obs(3, "13")],
    ]
    for obs in cases:
        seg, score = best_segment(obs, 1, 9, P)
        assert score_uncounted(obs, 1, 9, P) == pytest.approx(
            _plain_uncounted(obs)
        )
        if seg is not None:
            assert score == pytest.approx(score_segment(obs, seg, 1, 9, P))


def _plain_uncounted(obs):
    from scriptor.reflow.pagination.plan import _by_position

    return -P.mu * sum(max(o.weight for o in g)
                       for g in _by_position(obs).values())


def test_the_fit_really_returns_the_best_scoring_plan():
    """The DP must agree with the score it claims to maximise.

    Total score is the sum of the segment scores minus one segment price per
    *junction* -- not one price per segment still to come. The latter makes the
    penalty grow as lam*k*(k-1)/2 instead of lam*(k-1), so in a volume with
    several jumps the later boundaries become unaffordable, and the fit pays for
    it by overruling printed labels: at Carlomagno, whose PDF drops the blank
    before every chapter opening, pages printing 9, 10 and 11 came out as 10, 11
    and 12.

    Checked against exhaustive enumeration rather than a hand-picked example.
    The mis-costing only changes the answer where a short stretch competes with
    a long one and the tail is long -- exactly the shape that is hard to pick by
    hand and easy to get wrong.
    """
    from itertools import combinations

    from scriptor.reflow.pagination.plan import best_segment, score_uncounted

    # A short opening stretch, then a long one, then four more jumps: three
    # printed labels are all that stands against merging the first two.
    obs = [_obs(p, str(p)) for p in (1, 2, 3)]
    for k, (lo, hi) in enumerate(
        [(4, 16), (16, 24), (24, 32), (32, 40), (40, 48)], start=1
    ):
        obs += [_obs(p, str(p + k)) for p in range(lo, hi)]
    bounds = [1, 4, 16, 24, 32, 40]
    last = 47

    def total(starts):
        out = 0.0
        for k, start in enumerate(starts):
            stop = starts[k + 1] if k + 1 < len(starts) else last + 1
            _seg, s = best_segment(obs, start, stop, P)
            out += max(s, score_uncounted(obs, start, stop, P))
        return out - P.lam * (len(starts) - 1)

    best = max(total([1, *rest]) for r in range(len(bounds))
               for rest in combinations(bounds[1:], r))

    plan = fit(obs, boundaries=bounds, last_pos=last, params=P)
    starts = [s.start_pos for s in plan.segments]
    assert total(starts) == best
    assert starts == bounds
