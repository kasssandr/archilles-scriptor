"""Footnote numbering that restarts on every page, in a paragraph that spans the
page break.

The paragraph is the unit the renderer attaches footnotes to, but the number
printed next to a footnote is only unique *within its page*. A paragraph that
runs across a page break therefore sees two different footnotes both called "1".
Identifying them by that number loses one of them — silently, which is the one
failure mode this project exists to prevent.

See KONZEPT_scriptor_v2.md §5.8: the note model must not hard-wire "page-local".
"""
import re

from scriptor.reflow.core import main as reflow_main
from scriptor.reflow.regions import strip_metadata_block

# Both pages number their footnotes 1) and 2). Both paragraphs' lines are long
# enough not to trigger the paragraph-end heuristic, so the body runs on across
# the page break — the ordinary case in any printed book.
PAGE_1 = (
    "Erster Satz mit Note1 und ein zweiter Satz mit Note2 laeuft hier weiter\n"
    "1) Erste Note auf Seite eins.\n"
    "2) Zweite Note auf Seite eins.\n"
    "1\n"
)
PAGE_2 = (
    "und der dritte Satz mit Note1 nennt einen vierten mit Note2 am Ende.\n"
    "1) Erste Note auf Seite zwei.\n"
    "2) Zweite Note auf Seite zwei.\n"
    "2\n"
)


def _reflow(tmp_path, fmt="md"):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "00000001.txt").write_text(PAGE_1, encoding="utf-8")
    (pages / "00000002.txt").write_text(PAGE_2, encoding="utf-8")
    out = tmp_path / f"book.{fmt}"
    reflow_main(str(pages), str(out), fmt)
    # Without its §4.1 metadata block, so that "the first paragraph" below
    # means the first paragraph of the text.
    return strip_metadata_block(out.read_text(encoding="utf-8"))


def test_the_paragraph_really_spans_the_page_break(tmp_path):
    """Guards the premise of every other test in this file. If the paragraph-end
    heuristic ever splits these two pages, the collision cannot arise and the
    tests below would pass while proving nothing."""
    text = _reflow(tmp_path)
    first_paragraph = text.split("\n\n")[0]
    assert "[p. 1]" in first_paragraph and "[p. 2]" in first_paragraph


def test_no_footnote_text_is_lost_across_the_page_break(tmp_path):
    text = _reflow(tmp_path)
    for expected in (
        "Erste Note auf Seite eins.",
        "Zweite Note auf Seite eins.",
        "Erste Note auf Seite zwei.",
        "Zweite Note auf Seite zwei.",
    ):
        assert expected in text, f"footnote text lost: {expected!r}"


def test_four_distinct_footnote_definitions_are_emitted(tmp_path):
    text = _reflow(tmp_path)
    defs = re.findall(r"^\[\^(\d+)\]: ", text, re.M)
    assert sorted(defs) == ["1", "2", "3", "4"], f"definitions: {defs}"


def test_each_body_marker_is_referenced_exactly_once(tmp_path):
    """Two footnotes must never collapse into one Pandoc id. A duplicate [^1]
    means one note's text was overwritten by the other's."""
    text = _reflow(tmp_path)
    body = text.split("\n\n")[0]
    refs = re.findall(r"\[\^(\d+)\]", body)
    assert refs == ["1", "2", "3", "4"], f"body markers: {refs}"


def test_txt_mode_keeps_all_four_notes(tmp_path):
    text = _reflow(tmp_path, fmt="txt")
    assert text.count("Note auf Seite eins.") == 2
    assert text.count("Note auf Seite zwei.") == 2


def test_render_book_does_not_depend_on_page_index():
    """The disambiguator must not rely on Page.index: only reflow_main populates
    it, so a caller that builds Pages directly would silently get the collision
    back. Both pages here leave index at its default."""
    from scriptor.reflow.core import Page, render_book

    p1 = Page(1, ["Erster Teil des Absatzes mit Note [1] darin und er laeuft"],
              {1: "Note von Seite eins."}, mode="main")
    p2 = Page(2, ["weiter auf der Folgeseite mit Note [1] darin am Ende."],
              {1: "Note von Seite zwei."}, mode="main")
    assert p1.index == -1 and p2.index == -1

    # threshold=10: every line is longer, so the paragraph-end heuristic never
    # fires and the two pages really do form one paragraph.
    out, _audit = render_book([p1, p2], threshold=10, fmt="md")

    body = out.split("\n\n")[0]
    # Without this the test would pass vacuously: two paragraphs cannot collide.
    assert "[p. 1]" in body and "[p. 2]" in body, "pages did not share a paragraph"

    assert "Note von Seite eins." in out
    assert "Note von Seite zwei." in out
    assert out.count("[^1]:") == 1        # no definition emitted twice
    assert out.count("[^2]:") == 1
