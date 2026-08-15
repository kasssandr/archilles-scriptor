"""Recto: a section begins on the right, so a segment begins on an odd page.

Not the recto rule that was struck in stage 3. That one asked whether a *chapter
opening* sits on an odd page, and it depended on chapter detection -- 17 % to
100 % per volume, which is a measurement of the detector rather than of the
book.

This one asks where a *segment* begins, which is a rarer and far better attested
event: the offset between physical and printed page changes only where the PDF
dropped a blank, and the blank was there because the next section had to start
on the right. Measured over the corpus, 22 of 26 counted segment heads are odd,
and all four exceptions are Gli Actus -- exactly the four boundaries the user's
hand analysis showed to be one page late.

The other half of the rule is the offset jump: a section title page and its
blank verso are two deleted pages, so a jump of two says a section one page long
sits between them. That is the shape the fit could not see at all.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.observation import Observation
from scriptor.reflow.pagination.plan import FitParams, best_segment, fit
from scriptor.reflow.pagination.witnesses import boundary_candidates, printed_observations

P = FitParams()


def _obs(pos, label, weight=1.0, source="printed-bottom"):
    return Observation(pos=pos, label=label, source=source, weight=weight,
                       why="test")


def _page(index, label=None):
    return Page(num=-1, body_lines=["Text."], index=index, label_bottom=label)


# ── the candidate has to be on the ballot ────────────────────────────

def test_a_silent_page_before_a_break_may_start_a_segment():
    # Gli Actus prints nothing on the page that opens BIBLIOGRAFIA and prints
    # 312 on the page after it. Only the second is a break, so only the second
    # was ever proposed -- and the section really begins on the first.
    pages = [_page(i, str(i - 1)) for i in range(2, 6)]
    pages += [_page(6), _page(7, "8"), _page(8, "9")]
    obs = printed_observations(pages)
    assert 6 in boundary_candidates(pages, obs)


def test_a_page_that_speaks_is_not_proposed_twice():
    # The extra candidate is for pages that say nothing. Where a page carries a
    # reading, the break it makes is already on the ballot, and a second
    # candidate would only give a misreading another place to hide.
    pages = [_page(i, str(i)) for i in range(1, 6)]
    obs = printed_observations(pages)
    assert boundary_candidates(pages, obs) == [1]


# ── the penalty ──────────────────────────────────────────────────────

def test_a_segment_starting_on_a_verso_is_penalised():
    seg_odd, score_odd = best_segment([_obs(1, "11"), _obs(2, "12")], 1, 4, P)
    seg_even, score_even = best_segment([_obs(1, "12"), _obs(2, "13")], 1, 4, P)
    assert seg_odd.start_label == "11" and seg_even.start_label == "12"
    assert score_odd > score_even


def test_the_penalty_never_outweighs_a_reading():
    # Where the pages themselves say the segment starts even, they win. The rule
    # is a tie-break for what nobody observed, not a claim about the book.
    obs = [_obs(1, "12"), _obs(2, "13"), _obs(3, "14")]
    seg, _ = best_segment(obs, 1, 5, P)
    assert seg.start_label == "12"


def test_the_penalty_is_smaller_than_a_contradiction():
    # Otherwise a volume that does not follow recto would be re-numbered to fit
    # the rule rather than the page.
    assert 0 < P.rho < P.mu


# ── what it does to a volume ─────────────────────────────────────────

def test_the_boundary_moves_onto_the_silent_page():
    # Five pages print 1..5. Then a section opens on physical 6, which prints
    # nothing, and the pages after it print 8..11: the PDF dropped the blank
    # that put the section on the right, so printed 6 is gone and the section
    # itself is printed 7.
    #
    # Both placements explain every reading. Only one of them puts the section
    # on a recto, and that is the silent page.
    obs = [_obs(p, str(p)) for p in range(1, 6)]
    obs += [_obs(p, str(p + 1)) for p in range(7, 11)]
    plan = fit(obs, boundaries=[1, 6, 7], last_pos=10, params=P)
    starts = [(s.start_pos, s.start_label) for s in plan.segments
              if s.kind == "counted"]
    assert starts == [(1, "1"), (6, "7")]


def test_a_volume_that_paginates_evenly_is_left_alone():
    obs = [_obs(p, str(p + 1)) for p in range(1, 8)]
    plan = fit(obs, boundaries=[1], last_pos=7, params=P)
    assert [(s.start_pos, s.start_label) for s in plan.segments] == [(1, "2")]
