"""Scoring: which segment explains the most of what the witnesses said.

The fit knows nothing but observations, so these tests build them by hand -- no
PDF, no pages, no pipeline.
"""

from scriptor.reflow.pagination.observation import Observation
from scriptor.reflow.pagination.plan import FitParams, best_segment

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
