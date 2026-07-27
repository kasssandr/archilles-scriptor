"""End-to-end over the runner: truth + candidate file -> report."""
from pathlib import Path

from scriptor.eval.report import render_json, render_markdown
from scriptor.eval.runner import evaluate_file

TRUTH = """
volume = "demo"
pages = ["1"]
[[footnotes]]
page = "1"
num = 1
anchor_after = "with a note"
definition_starts = "Only note"
status = "intact"
"""

CANDIDATE = """[p. 1] A line with a note [^1] in it.

[^1]: Only note text.
"""


def test_evaluate_file_and_render(tmp_path: Path):
    tp = tmp_path / "truth.toml"; tp.write_text(TRUTH, encoding="utf-8")
    cp = tmp_path / "scriptor.review.md"; cp.write_text(CANDIDATE, encoding="utf-8")
    rep = evaluate_file(tp, cp, adapter="prepared")
    assert rep.volume == "demo" and rep.candidate == "scriptor.review"
    assert rep.anchors.anchor_rate == 1.0

    md = render_markdown([rep])
    assert "| demo |" in md and "100%" in md
    js = render_json([rep])
    assert '"anchor_rate": 1.0' in js


def test_cli_run_prints_report(tmp_path: Path, capsys):
    from scriptor.cli import main
    tp = tmp_path / "truth.toml"; tp.write_text(TRUTH, encoding="utf-8")
    cp = tmp_path / "out.review.md"; cp.write_text(CANDIDATE, encoding="utf-8")
    main(["eval", "run", "--truth", str(tp), "--candidate", str(cp)])
    out = capsys.readouterr().out
    assert "Anchor" in out and "100%" in out
