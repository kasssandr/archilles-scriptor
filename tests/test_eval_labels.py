"""Page-label fidelity: the printed label is the citation address."""
from scriptor.eval.adapters import ParsedDoc
from scriptor.eval.ground_truth import loads_truth
from scriptor.eval.labels import evaluate_labels

TRUTH = loads_truth('volume="t"\npages=["xiv","1","2","3"]\n')


def _doc(labels):
    return ParsedDoc(body="", page_marks=[(l, i) for i, l in enumerate(labels)])


def test_perfect_sequence():
    res = evaluate_labels(TRUTH, _doc(["xiv", "1", "2", "3"]))
    assert (res.found, res.missing, res.extra) == (4, 0, 0)
    assert res.label_fidelity == 1.0


def test_dropped_and_renumbered():
    # tool dropped "xiv" and renumbered pages physically 1..4
    res = evaluate_labels(TRUTH, _doc(["1", "2", "3", "4"]))
    assert res.found == 3            # 1,2,3 match
    assert res.missing == 1          # xiv
    assert res.extra == 1            # the physical "4"
    assert res.label_fidelity == 0.75


def test_no_labels_at_all():
    res = evaluate_labels(TRUTH, _doc([]))
    assert res.label_fidelity == 0.0 and res.missing == 4


def test_a_wrong_label_is_counted_as_wrong_not_merely_missing():
    # The volume prints "1" on its second page; the tool claims "9" there.
    # Counting that only as "missing 1, extra 9" hides that a citation built on
    # it points at the wrong page — the failure the source consensus can newly
    # produce.
    res = evaluate_labels(TRUTH, _doc(["xiv", "9", "2", "3"]))
    assert res.wrong == 1


def test_a_perfect_sequence_has_nothing_wrong():
    res = evaluate_labels(TRUTH, _doc(["xiv", "1", "2", "3"]))
    assert res.wrong == 0


def test_a_missing_label_is_not_wrong():
    # Nothing is claimed at that position, so nothing is claimed falsely.
    res = evaluate_labels(TRUTH, _doc(["xiv", "1", "3"]))
    assert res.wrong == 0
