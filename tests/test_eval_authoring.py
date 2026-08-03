"""Page selection must be reproducible and must stay inside the body range."""
import pytest

from scriptor.eval.authoring import PageRef, choose_pages


def _refs(n: int) -> list[PageRef]:
    """n physical pages; the first four carry roman labels like real frontmatter."""
    roman = ["i", "ii", "iii", "iv"]
    return [PageRef(index=i + 1, label=roman[i] if i < 4 else str(i - 3))
            for i in range(n)]


def test_same_seed_gives_same_pages():
    refs = _refs(60)
    a = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    b = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    assert a == b
    assert len(a) == 10


def test_different_seed_gives_different_pages():
    refs = _refs(60)
    a = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    b = choose_pages(refs, body_range=(5, 60), count=10, seed=7)
    assert a != b


def test_selection_stays_inside_body_range():
    refs = _refs(60)
    chosen = choose_pages(refs, body_range=(5, 20), count=8, seed=42)
    labels_in_range = {r.label for r in refs if 5 <= r.index <= 20}
    assert set(chosen) <= labels_in_range
    assert "i" not in chosen and "iv" not in chosen   # frontmatter excluded


def test_result_is_sorted_by_physical_order():
    refs = _refs(60)
    chosen = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    order = {r.label: r.index for r in refs}
    assert [order[c] for c in chosen] == sorted(order[c] for c in chosen)


def test_asking_for_more_than_available_is_refused():
    with pytest.raises(ValueError):
        choose_pages(_refs(60), body_range=(5, 10), count=20, seed=42)


def test_labels_are_returned_not_indices():
    chosen = choose_pages(_refs(60), body_range=(5, 60), count=3, seed=1)
    assert all(isinstance(c, str) for c in chosen)
