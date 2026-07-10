"""Two findings from proofreading Zuckerman chapter 2 against the PDF.

First: a paragraph ends on "preserved the Occident.” 1" — after marker
substitution the line ends on "[1]", the sentence-end heuristic no longer sees
the full stop, and the paragraph runs on. The marker must be transparent to
the paragraph-end check.

Second: FineReader renders the ʿayn of Arabic transliterations as an asterisk
("*Abbasid", "*Abd ar-Rahman"). Two of those in one paragraph form a Markdown
emphasis pair — the asterisks vanish from the reading view and everything
between them turns italic. Literal * and _ must be escaped in md output; the
characters themselves stay verbatim (no transliteration guessing).
"""

from scriptor.reflow.core import Page, format_paragraph_md, reconstruct_body


def test_a_trailing_marker_does_not_hide_the_paragraph_end():
    page = Page(num=36, body_lines=[
        "so here the intact forces of Austrasia, the vassals of the",
        "preserved the Occident.” [1]",
        "The role of the inhabitants of Narbonne during the siege of",
        "the fortress, and their status thereafter, have long been obscure.",
    ], footnotes={1: "H. Pirenne, Mohammed and Charlemagne, p. 157."})
    paras, _fns, _occs, _levels = reconstruct_body([page], threshold=40)
    assert len(paras) == 2
    assert paras[0].endswith("[1]")
    assert paras[1].startswith("The role of the inhabitants")


def test_two_trailing_markers_are_also_transparent():
    page = Page(num=53, body_lines=[
        "divided up the lands between the conquerors and the former",
        "inhabitants of the country. [4] [5]",
        "Jews would be certainly included among the former inhabitants",
        "and their part in the life of the town is beyond any doubt.",
    ], footnotes={4: "eins", 5: "zwei"})
    paras, _fns, _occs, _levels = reconstruct_body([page], threshold=40)
    assert len(paras) == 2


def _md(para, fns=None, occs=None, level=0):
    state = {"counter": 0, "defs": []}
    return format_paragraph_md(para, fns or {}, occs or {}, level, state), state


def test_literal_asterisks_are_escaped_in_md():
    out, _ = _md("first the *Abbasid, then the *Umayyad, dynasty based in Spain")
    assert r"\*Abbasid" in out and r"\*Umayyad" in out


def test_literal_underscores_are_escaped_in_md():
    out, _ = _md("the file was named notes_on_narbonne by its scribe")
    assert r"notes\_on\_narbonne" in out


def test_footnote_definitions_are_escaped_too():
    out, state = _md(
        "allied himself with the refugee. [3]",
        fns={(0, 3): "F. W. Buckler on the *Abbasid interests in Spain."},
        occs={0: (0, 3)},
    )
    assert "[^1]" in out
    assert state["defs"] == [r"[^1]: F. W. Buckler on the \*Abbasid interests in Spain."]


def test_our_own_constructs_stay_untouched():
    out, _ = _md("ein Satz mit Marker [p. 36] und weiter im Text")
    assert "[p. 36]" in out
