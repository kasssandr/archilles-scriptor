"""The decision sidecar and its application.

The pipeline is deterministic, so a correction is expressed as a decision and
replayed, not as an edit to the rendered Markdown (which cannot be read back).
See src/scriptor/reflow/decisions.py.
"""
import pytest

from scriptor.reflow import decisions as dec
from scriptor.reflow.core import Page, render_book


def _pages():
    """One paragraph spanning two pages. Page 1 prints footnotes 1..3, but the
    marker of footnote 2 was misread as the 'z' ending "Werkz". Page 2 carries
    footnotes 5 and 6, both anchored."""
    p1 = Page(1, ["Anfang [1] dann das Werkz weiter [3] und es laeuft"],
              {1: "eins-1", 2: "eins-2", 3: "eins-3"}, mode="main")
    p2 = Page(2, ["weiter mit [5] und noch [6] am Ende."],
              {5: "zwei-5", 6: "zwei-6"}, mode="main")
    return [p1, p2]


def _render(decisions=None):
    # threshold=10: every line is longer, so the two pages share one paragraph.
    out, _audit = render_book(_pages(), threshold=10, fmt="md", decisions=decisions)
    return out


def _defs(out):
    return [ln.split(": ", 1)[1] for ln in out.splitlines() if ln.startswith("[^")]


# --- parsing ------------------------------------------------------------------

def test_unmarked_lines_are_not_decisions():
    d = dec.parse("[ ] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: x")
    assert not d.accepted and not d


def test_marked_line_is_a_decision():
    d = dec.parse("[x] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: x")
    assert d.accepted == {("1", 6): 1}
    assert d


def test_roman_page_label_is_addressable():
    d = dec.parse("[x] p. xiv  fn 2  cand 1  'z'  conf 0.8  ctx: x")
    assert d.accepted == {("xiv", 2): 1}


def test_two_candidates_for_one_footnote_is_refused_not_guessed():
    text = ("[x] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: x\n"
            "[x] p. 1  fn 6  cand 2  'b'  conf 0.5  ctx: y\n")
    with pytest.raises(dec.AmbiguousDecision):
        dec.parse(text)


def test_comments_and_noise_are_ignored():
    d = dec.parse("# a comment\n\nnot a line at all\n[x] p. 2  fn 1  cand 1  'l'  conf 0.7  ctx: z\n")
    assert d.accepted == {("2", 1): 1}


# --- template -----------------------------------------------------------------

def test_template_round_trips_through_the_parser():
    from scriptor.reflow.confidence import Annotator
    ann = Annotator()
    ann.annotate("[p. 1] Anfang [1] dann das Werkz weiter [3] Ende",
                 {1: "a", 2: "b", 3: "c"})
    text = dec.render_template(ann.annotations, "book.md", "book.md.decisions.txt")
    # Nothing is accepted until a human marks it.
    assert not dec.parse(text).accepted
    # And marking it yields exactly the footnote it describes.
    assert dec.parse(text.replace("[ ]", "[x]", 1)).accepted


# --- application --------------------------------------------------------------

def test_without_decisions_the_footnote_stays_a_hanging_reference():
    out = _render()
    assert "Werkz" in out                    # glyph untouched
    assert "eins-2" in out                   # text never lost
    assert "weiter [^2][^3]" in out          # synthetic anchor before [3] (spec §4.3)
    assert _defs(out)[1] == "eins-2"         # defs stay in printed order


def test_accepted_candidate_replaces_the_glyph_with_a_marker():
    out = _render(dec.Decisions(accepted={("1", 2): 1}))
    assert "das Werk[^2] weiter" in out
    assert "Werkz" not in out                # the misread glyph is gone


def test_placing_a_marker_keeps_every_footnote_with_its_own_page():
    """The inserted marker shifts every [N] occurrence after it. If the occurrence
    map is not rebuilt, page 2's footnotes are silently reattached to page 1's
    numbers — the exact corruption FnKey exists to prevent."""
    out = _render(dec.Decisions(accepted={("1", 2): 1}))
    assert _defs(out) == ["eins-1", "eins-2", "eins-3", "zwei-5", "zwei-6"]
    body = out.split("\n\n")[0]
    assert body.count("[^") == 5
    assert not body.rstrip().endswith("]") or "am Ende." in body  # no hanging ref


def test_decision_is_idempotent():
    d1 = dec.Decisions(accepted={("1", 2): 1})
    d2 = dec.Decisions(accepted={("1", 2): 1})
    assert _render(d1) == _render(d2)


def test_decision_for_a_nonexistent_candidate_is_reported_not_guessed():
    d = dec.Decisions(accepted={("1", 2): 7})   # only one candidate exists
    out = _render(d)
    assert d.unmatched == [("1", 2)]
    assert d.applied == []
    assert "Werkz" in out                       # nothing was placed
    assert "eins-2" in out                      # nothing was lost


def test_decision_for_an_unknown_footnote_changes_nothing():
    d = dec.Decisions(accepted={("9", 4): 1})
    assert _render(d) == _render()
    assert d.applied == []


# --- CLI surface --------------------------------------------------------------

def _pages_dir(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "00000001.txt").write_text(
        "Erstens5 dann das Werk& und hinten7 als Schluss folgt es hier.\n"
        "5) Fuenfte Note.\n6) Sechste Note.\n7) Siebte Note.\n1\n",
        encoding="utf-8",
    )
    return pages


def test_cli_writes_a_decision_template_and_applies_it(tmp_path, capsys):
    from scriptor.cli import main as cli

    pages = _pages_dir(tmp_path)
    out = tmp_path / "book.md"
    assert cli(["reflow", str(pages), "--out", str(out)]) == 0

    template = tmp_path / "book.md.decisions.txt"
    assert "[ ] p. 1  fn 6  cand 1" in template.read_text(encoding="utf-8")
    assert "Werk&" in out.read_text(encoding="utf-8")

    template.write_text(
        template.read_text(encoding="utf-8").replace("[ ] p. 1  fn 6", "[x] p. 1  fn 6"),
        encoding="utf-8",
    )
    assert cli(["reflow", str(pages), "--out", str(out), "--decisions", str(template)]) == 0

    corrected = out.read_text(encoding="utf-8")
    assert "Werk[^2]" in corrected and "Werk&" not in corrected
    # Nothing is left to decide, so the regenerated template lists no candidate.
    assert "[ ] p." not in template.read_text(encoding="utf-8")


def test_cli_refuses_an_ambiguous_decision_with_exit_code_2(tmp_path, capsys):
    from scriptor.cli import main as cli

    pages = _pages_dir(tmp_path)
    out = tmp_path / "book.md"
    cli(["reflow", str(pages), "--out", str(out)])
    marks = tmp_path / "d.txt"
    marks.write_text(
        "[x] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: x\n"
        "[x] p. 1  fn 6  cand 2  'b'  conf 0.5  ctx: y\n",
        encoding="utf-8",
    )
    assert cli(["reflow", str(pages), "--out", str(out), "--decisions", str(marks)]) == 2
    assert "two candidates marked" in capsys.readouterr().err


def test_cli_reports_a_missing_decision_file_with_exit_code_2(tmp_path, capsys):
    from scriptor.cli import main as cli

    pages = _pages_dir(tmp_path)
    out = tmp_path / "book.md"
    assert cli(["reflow", str(pages), "--out", str(out),
                "--decisions", str(tmp_path / "absent.txt")]) == 2
    assert "file not found" in capsys.readouterr().err
