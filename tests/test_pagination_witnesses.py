"""What each source says about a page, and where a segment may begin."""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.witnesses import (
    boundary_candidates,
    catalogue_observations,
    catalogue_weight,
    printed_observations,
)


def _page(index, bottom=None, top=None, backend=None):
    return Page(num=-1, body_lines=["Text."], index=index,
                label_bottom=bottom, label_top=top, backend_label=backend)


def test_both_edges_are_asked():
    pages = [_page(1, bottom="11", top="77")]
    got = {(o.source, o.label) for o in printed_observations(pages)}
    assert got == {("printed-bottom", "11"), ("printed-top", "77")}


def test_a_page_without_a_physical_index_is_not_asked():
    # No index, no distance; without a distance no sequence can be checked.
    pages = [Page(num=-1, body_lines=["Text."], label_bottom="11")]
    assert printed_observations(pages) == []


def test_the_catalogue_weighs_what_it_gets_right():
    pages = [_page(i, bottom=str(i), backend=str(i)) for i in range(1, 6)]
    assert catalogue_weight(pages) == 1.0
    assert len(catalogue_observations(pages, 1.0)) == 5


def test_a_catalogue_that_agrees_with_nothing_weighs_nothing():
    # Bauer: 339 of 339 pages off by one. As a stater of values it is worth
    # nothing; its structure is used from stage 2 on, not its numbers.
    pages = [_page(i, bottom=str(i), backend=str(i - 1)) for i in range(2, 8)]
    assert catalogue_weight(pages) == 0.0
    assert catalogue_observations(pages, 0.0) == []


def test_a_catalogue_too_small_to_check_weighs_nothing():
    # Two overlapping pages cannot tell a real catalogue from a mechanical one.
    pages = [_page(1, bottom="1", backend="1"), _page(2, bottom="2", backend="2")]
    assert catalogue_weight(pages) == 0.0


def test_a_broken_run_proposes_a_boundary():
    pages = [_page(1, bottom="1"), _page(2, bottom="2"),
             _page(3, bottom="4"), _page(4, bottom="5")]
    obs = printed_observations(pages)
    assert 3 in boundary_candidates(pages, obs)


def test_a_consistent_run_proposes_no_interior_boundary():
    pages = [_page(i, bottom=str(i)) for i in range(1, 6)]
    obs = printed_observations(pages)
    assert boundary_candidates(pages, obs) == [1]


def test_a_change_of_numbering_proposes_a_boundary():
    pages = [_page(1, bottom="vii"), _page(2, bottom="viii"),
             _page(3, bottom="1"), _page(4, bottom="2")]
    obs = printed_observations(pages)
    assert 3 in boundary_candidates(pages, obs)


def test_the_catalogue_proposes_its_own_boundaries():
    # Where the catalogue changes numbering, the volume plausibly does too --
    # even when the catalogue's values are wrong.
    pages = [_page(1, backend="ii"), _page(2, backend="iii"),
             _page(3, backend="1"), _page(4, backend="2")]
    assert 3 in boundary_candidates(pages, [])


def test_where_the_counting_would_have_started_is_a_candidate():
    # Themistios prints "2" on physical page 17: the arabic count starts at 16,
    # and no segment may begin further back, because its value would be below 1.
    pages = [_page(i) for i in range(14, 17)] + [_page(17, bottom="2")]
    obs = printed_observations(pages)
    assert 16 in boundary_candidates(pages, obs)


def test_a_volume_counting_its_title_pages_starts_at_one():
    # Bauer prints "7" on its seventh physical page.
    pages = [_page(i) for i in range(1, 7)] + [_page(7, bottom="7")]
    obs = printed_observations(pages)
    assert boundary_candidates(pages, obs) == [1]


def test_a_running_head_at_the_wrong_edge_does_not_propose_boundaries():
    # The same head on every page, carrying a chapter number that never moves.
    # Read as a folio it breaks the run at every single page; it must not be
    # allowed to litter the volume with boundary candidates.
    pages = [_page(i, bottom=str(i), top="12") for i in range(1, 8)]
    obs = printed_observations(pages)
    assert boundary_candidates(pages, obs) == [1]
