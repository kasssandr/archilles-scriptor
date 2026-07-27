"""Normalization must be tolerant (case, whitespace runs, soft hyphens,
line-break hyphenation) while find_snippet reports offsets in the ORIGINAL
string, so metric anchors can be compared against unmodified output text."""
from scriptor.eval.normalize import find_snippet, normalize


def test_normalize_collapses_whitespace_and_case():
    assert normalize("Zwei  Wörter\nhier") == "zwei wörter hier"


def test_normalize_removes_soft_hyphen_and_joins_wrap_hyphen():
    # soft hyphen U+00AD vanishes; "Zei-\nle" rejoins to "zeile"
    assert normalize("Zei­le") == "zeile"
    assert normalize("Zei-\nle") == "zeile"


def test_find_snippet_reports_original_offsets():
    hay = "Der Text  mit  UNGLEICHEN Abständen."
    span = find_snippet(hay, "mit ungleichen")
    assert span is not None
    start, end = span
    assert hay[start:end] == "mit  UNGLEICHEN"


def test_find_snippet_none_when_absent():
    assert find_snippet("abc", "xyz") is None


def test_find_snippet_across_linebreak_hyphen():
    hay = "eine Fußno-\nte im Umbruch"
    span = find_snippet(hay, "Fußnote im")
    assert span is not None
    start, end = span
    assert hay[start:end].startswith("Fußno-")
