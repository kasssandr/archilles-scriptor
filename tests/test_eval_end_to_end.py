"""Golden loop: scriptor's own pipeline over the committed synthetic volume,
evaluated by the harness. This is the harness's harness — if these numbers
move, either the pipeline or a metric changed behaviour.

The volume uses continuous footnote numbering (1..7): the pipeline dedups
present markers by number across the merged document, so page-local numbers
would let only the last note per number be flagged. Continuous numbers let the
volume exercise a suggested flag (note 2), an orphan flag (note 5) and a
hanging reference over a page boundary (note 7)."""
from pathlib import Path

from scriptor.eval.runner import evaluate_file
from scriptor.reflow import core

GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "golden" / "synthetic-de"


def test_synthetic_volume_scores(tmp_path: Path):
    out = tmp_path / "book.md"
    core.main(str(GOLDEN / "pages"), str(out))
    review = tmp_path / "book.review.md"
    assert review.exists()

    rep = evaluate_file(GOLDEN / "truth.toml", review, adapter="prepared")
    statuses = {(o.truth.page, o.truth.num): o.status for o in rep.anchors.outcomes}
    assert statuses[("1", 1)] == "anchored_exact"
    assert statuses[("1", 2)] == "flagged"           # suggested via a 'z' glyph
    assert statuses[("1", 3)] == "anchored_exact"
    assert statuses[("2", 5)] == "flagged"           # orphan flag, no candidate
    assert statuses[("3", 7)] in ("anchored_page", "flagged")  # hanging at page bound
    assert rep.anchors.silent_damage_rate == 0.0
    assert rep.labels.label_fidelity == 1.0
    assert rep.citations.emitted is False
