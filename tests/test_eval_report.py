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


REGION_TRUTH = TRUTH + """
[[regions]]
from_page = "1"
name = "main"

[[regions]]
from_page = "2"
name = "bibliography"
"""

# Definitions are collected at the document end (spec §4.3), so every page and
# every region marker stands above them.
REGION_CANDIDATE = """[region: main]

[p. 1] A line with a note [^1] in it.

[region: bibliography]

[p. 2] Aerts, W. J. 2003.

[^1]: Only note text.
"""


def test_report_carries_region_recall(tmp_path: Path):
    tp = tmp_path / "truth.toml"; tp.write_text(REGION_TRUTH, encoding="utf-8")
    cp = tmp_path / "s.review.md"; cp.write_text(REGION_CANDIDATE, encoding="utf-8")
    rep = evaluate_file(tp, cp, adapter="prepared")
    assert rep.regions.exact_recall == 1.0
    assert rep.regions.blocks_found == 2


def test_markdown_names_a_missed_region_rather_than_only_a_rate(tmp_path: Path):
    """A rate cannot be acted on; the name of the region that went unseen can."""
    tp = tmp_path / "truth.toml"; tp.write_text(REGION_TRUTH, encoding="utf-8")
    cp = tmp_path / "s.review.md"
    cp.write_text(REGION_CANDIDATE.replace("[region: bibliography]\n\n", ""),
                  encoding="utf-8")
    md = render_markdown([evaluate_file(tp, cp, adapter="prepared")])
    assert "bibliography" in md


def test_volume_without_region_truth_shows_a_dash(tmp_path: Path):
    tp = tmp_path / "truth.toml"; tp.write_text(TRUTH, encoding="utf-8")
    cp = tmp_path / "s.review.md"; cp.write_text(CANDIDATE, encoding="utf-8")
    md = render_markdown([evaluate_file(tp, cp, adapter="prepared")])
    assert "Regions" in md.splitlines()[0]
    assert md.splitlines()[2].rstrip().endswith("| — |")
