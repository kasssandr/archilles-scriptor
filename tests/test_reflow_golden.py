"""Characterization (golden) test for the reflow pipeline.

Locks the current reflow output (md + txt + audit) on a small multi-page
fixture so the footnotes.py extraction (Etappe 2-A) can be proven
behaviour-preserving: the output must stay byte-identical before and after
the refactor. The fixture deliberately exercises the footnote-relevant paths:
a footnote whose marker is found in the body (-> [^1]), a footnote definition
whose marker is missing (-> hanging reference [^2] + audit entry), [S. NN]
page markers, and a soft-hyphenated word rejoined across a line break.
"""

from pathlib import Path

from scriptor.reflow.core import main as reflow_main

FIXTURE = Path(__file__).parent / "fixtures" / "reflow_golden"
PAGES = FIXTURE / "pages"
CONF = Path(__file__).parent / "fixtures" / "reflow_confidence"
CONF_PAGES = CONF / "pages"


def _audit_body(text: str) -> list[str]:
    # Drop the first header line — it embeds the output path, which differs
    # between the committed golden and the tmp test run. Everything below it
    # (the comment block and the "S. NN: FN …" data) is path-independent.
    return text.splitlines()[1:]


def test_reflow_md_matches_golden(tmp_path):
    out = tmp_path / "out.md"
    reflow_main(str(PAGES), str(out), "md")
    assert out.read_text(encoding="utf-8") == (
        FIXTURE / "expected.md"
    ).read_text(encoding="utf-8")
    assert _audit_body((tmp_path / "out.md.audit.txt").read_text(encoding="utf-8")) == _audit_body(
        (FIXTURE / "expected.md.audit.txt").read_text(encoding="utf-8")
    )


def test_reflow_txt_matches_golden(tmp_path):
    out = tmp_path / "out.txt"
    reflow_main(str(PAGES), str(out), "txt")
    assert out.read_text(encoding="utf-8") == (
        FIXTURE / "expected.txt"
    ).read_text(encoding="utf-8")


def test_reflow_md_clean_still_byte_identical(tmp_path):
    # book.md must not change when the confidence layer is present.
    out = tmp_path / "out.md"
    reflow_main(str(PAGES), str(out), "md")
    assert out.read_text(encoding="utf-8") == (
        FIXTURE / "expected.md"
    ).read_text(encoding="utf-8")


def test_reflow_review_master_leaves_unbounded_fn_unflagged(tmp_path):
    # FN 2 is unclaimed on page 2 but is NOT an interior gap — page 2's
    # paragraph has no recognised markers bounding it — so the confidence layer
    # conservatively leaves it unflagged. The review master then equals the
    # clean output for this fixture.
    out = tmp_path / "out.md"
    reflow_main(str(PAGES), str(out), "md")
    review = (tmp_path / "out.review.md").read_text(encoding="utf-8")
    assert review == (FIXTURE / "expected.review.md").read_text(encoding="utf-8")
    assert "[?FN" not in review


def test_reflow_confidence_fixture_has_vorgeschlagen_flag(tmp_path):
    out = tmp_path / "out.md"
    reflow_main(str(CONF_PAGES), str(out), "md")
    review = (tmp_path / "out.review.md").read_text(encoding="utf-8")
    assert review == (CONF / "expected.review.md").read_text(encoding="utf-8")
    assert "Werk&[?FN:6|&]" in review
