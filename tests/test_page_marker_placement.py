"""Where [p. NN] lands when a word is hyphenated across the page break.

The marker says which page the text after it is printed on. A word split by
the break cannot be cut in two by a marker, so the marker waits for the word
to be complete -- but no longer than that. Measured on the benchmark corpus,
4 of Bauer's 19 authored pages open with such a word fragment, and each of
them hands 65 to 69 characters of its own first line to the previous page.
"""
from scriptor.reflow.core import main as reflow_main

# Page 1 breaks "bestimmen" after "be-"; page 2 carries the rest. The lines are
# long enough that the paragraph-end heuristic keeps the paragraph running
# across the break, which is what puts the marker inside a line at all.
PAGE_1 = (
    "Die Technik der Reproduktion hat im letzten Jahrhundert begonnen, das\n"
    "alltaegliche Leben in seinen kleinsten Verrichtungen mit zu be-\n"
    "1\n"
)
PAGE_2 = (
    "stimmen und zu formen. Mit Smartphones werden staendig neue Bilder\n"
    "erzeugt und weitergegeben, was den Umgang mit dem Einzelbild aendert.\n"
    "2\n"
)


def _reflow(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "00000001.txt").write_text(PAGE_1, encoding="utf-8")
    (pages / "00000002.txt").write_text(PAGE_2, encoding="utf-8")
    out = tmp_path / "book.md"
    reflow_main(str(pages), str(out), "md")
    return out.read_text(encoding="utf-8")


def _body(text):
    """The prose after the YAML metadata block, which is itself a paragraph."""
    if text.startswith("---\n"):
        return text.split("\n---", 1)[1].lstrip("\n")
    return text


def test_the_paragraph_really_spans_the_page_break(tmp_path):
    """Guards the premise: if the paragraph ends at the page foot, the marker
    starts a fresh paragraph and there is nothing to place it inside of."""
    text = _reflow(tmp_path)
    first_paragraph = _body(text).split("\n\n")[0]
    assert "[p. 1]" in first_paragraph and "[p. 2]" in first_paragraph


def test_marker_follows_the_rejoined_word_not_the_whole_line(tmp_path):
    text = _reflow(tmp_path)
    assert "zu bestimmen [p. 2] und zu formen." in text
