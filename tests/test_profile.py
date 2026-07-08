"""The OCR profile: what a corrected corpus says the superscript digits look like.

Within one volume the evidence is free — count its own gaps. Across volumes there
is nothing to count, so what carries over is what a human confirmed, and that lives
in the decision sidecars. The profile is therefore an *explicit input file*, never
an accumulating side effect: same pages plus same profile plus same code give the
same decision file, which is the property the whole correction loop stands on.
"""
import json

import pytest

from scriptor.reflow import profile as prof
from scriptor.reflow.confidence import (
    BASE_PRIOR,
    NO_EVIDENCE,
    GlyphEvidence,
    analyse_paragraph,
    find_candidates,
)
from scriptor.reflow.decisions import AmbiguousDecision, read_lines
from scriptor.reflow.core import Page, document_evidence, render_book

# Two volumes' worth of decisions: footnote 1's marker was read as 'l' three times
# and as 'i' once; where both were offered, the human always took 'l'.
BOOK_A = """\
# comments are ignored
[x] p. 4   fn 1  cand 1  'l'  conf 0.8  ctx: ...
[ ] p. 4   fn 1  cand 2  'i'  conf 0.7  ctx: ...
[x] p. 9   fn 1  cand 1  'l'  conf 0.8  ctx: ...
[ ] p. 12  fn 1  cand 1  'i'  conf 0.8  ctx: ...
"""
BOOK_B = """\
[x] p. 3   fn 1  cand 1  'l'  conf 0.8  ctx: ...
[ ] p. 3   fn 1  cand 2  'j'  conf 0.6  ctx: ...
[x] p. 7   fn 6  cand 1  '&'  conf 0.9  ctx: ...
"""


def _profile():
    return prof.learn([("a.txt", BOOK_A), ("b.txt", BOOK_B)])


# --- reading the sidecars -----------------------------------------------------

def test_a_candidate_line_yields_its_glyph():
    lines = read_lines("[x] p. 4  fn 1  cand 1  'l'  conf 0.8  ctx: x")
    assert lines[0].marked and lines[0].glyph == "l" and lines[0].fn == 1


def test_an_apostrophe_glyph_survives_being_repr_ed():
    """OCR_CONFUSION[4] holds "'" itself, so repr() double-quotes that line."""
    lines = read_lines("""[x] p. 4  fn 4  cand 1  "'"  conf 0.8  ctx: x""")
    assert lines[0].glyph == "'"


# --- learning -----------------------------------------------------------------

def test_the_marked_candidate_is_a_confirmation_its_rivals_are_rejections():
    p = _profile()
    assert p.glyphs[1]["l"].accepted == 3      # p.4 and p.9 of A, p.3 of B
    assert p.glyphs[1]["i"].rejected == 1      # offered beside 'l' on p.4 of A
    assert p.glyphs[1]["j"].rejected == 1      # offered beside 'l' on p.3 of B
    assert p.glyphs[6]["&"].accepted == 1


def test_an_undecided_footnote_teaches_nothing():
    """p. 12 of A has a candidate but no mark. Undecided is not refused."""
    p = _profile()
    assert p.glyphs[1]["i"].accepted == 0
    assert p.glyphs[1]["i"].rejected == 1      # only the one beside a real choice


def test_learning_is_a_pure_function_of_its_inputs():
    """Running it again cannot double-count, because nothing is appended."""
    assert prof.dumps(_profile()) == prof.dumps(_profile())


def test_two_marks_for_one_footnote_are_refused():
    bad = ("[x] p. 1  fn 2  cand 1  'z'  conf 0.8  ctx: x\n"
           "[x] p. 1  fn 2  cand 2  'Z'  conf 0.7  ctx: y\n")
    with pytest.raises(AmbiguousDecision):
        prof.learn([("bad.txt", bad)])


def test_a_profile_with_no_marks_is_falsy():
    empty = prof.learn([("none.txt", "[ ] p. 1  fn 2  cand 1  'z'  conf 0.8  ctx: x")])
    assert not empty


# --- serialising --------------------------------------------------------------

def test_round_trip_through_json():
    p = _profile()
    back = prof.loads(prof.dumps(p))
    assert back.glyphs[1]["l"].accepted == 3
    assert back.sources == ["a.txt", "b.txt"]


def test_json_is_sorted_so_it_diffs_cleanly():
    text = prof.dumps(_profile())
    payload = json.loads(text)
    assert list(payload["glyphs"]) == ["1", "6"]
    assert list(payload["glyphs"]["1"]) == ["i", "j", "l"]


def test_an_unknown_schema_version_is_refused_not_guessed():
    with pytest.raises(ValueError, match="version"):
        prof.loads(json.dumps({"version": 99, "glyphs": {}}))


# --- how it enters scoring ----------------------------------------------------

def test_a_glyph_only_ever_rejected_contributes_nothing():
    pseudo = _profile().pseudo_counts()
    assert (1, "l") in pseudo
    assert (1, "i") not in pseudo      # rejected, never accepted -> prior floor
    assert (1, "j") not in pseudo


def test_a_profile_alone_just_reaches_the_belief_threshold():
    """So a fresh volume with no gaps of its own can still be ranked."""
    ev = GlyphEvidence(pseudo=_profile().pseudo_counts())
    assert ev.informed(1)
    assert ev.share(1, "l") == 1.0


def test_the_books_own_typography_outweighs_the_corpus():
    """Six sightings of 'i' in *this* scan beat three pseudo-observations of 'l'."""
    from collections import Counter

    ev = GlyphEvidence(Counter({(1, "i"): 6}), _profile().pseudo_counts())
    assert ev.share(1, "i") > ev.share(1, "l")
    assert ev.prior(1, "i")[0] > ev.prior(1, "l")[0]


def test_the_reason_says_the_profile_spoke():
    ev = GlyphEvidence(pseudo=_profile().pseudo_counts())
    _score, reason = ev.prior(1, "l")
    assert reason.endswith("+profile")


def test_without_a_profile_nothing_changes():
    ev = GlyphEvidence()
    assert ev.prior(1, "l") == (BASE_PRIOR, "glyph-in-table")


# --- the guardrails hold for the profile too ----------------------------------

def test_a_profile_cannot_add_a_candidate_the_table_does_not_know():
    """A corpus that confirmed '§' as a 2 still cannot make '§' a candidate: the
    candidate set is settled by the confusion table and the marker-position rule.
    Widening it is a change to the table, not something statistics may do."""
    ev = GlyphEvidence(pseudo={(2, "§"): 99.0})
    interval = " und Werk§ oder Werkz und "
    assert {c.char for c in find_candidates(interval, 0, 2, evidence=ev)} == {"z"}


def test_a_profile_cannot_open_a_gap():
    ev = GlyphEvidence(pseudo={(2, "z"): 99.0})
    para = "Ein Satz mit [1] und Werkz [2] und [3] hier."   # footnote 2 is anchored
    assert analyse_paragraph(para, {1: "a", 2: "b", 3: "c"}, evidence=ev) == []


# --- end to end ---------------------------------------------------------------

_ONE_GAP = "Er nennt Note [1] und Werkz sowie Marke [3]."


def _one_page():
    return [Page(1, [_ONE_GAP], {1: "a", 2: "b", 3: "c"}, mode="main")]


def test_a_profile_lets_a_thin_document_rank_its_candidates():
    """One gap is far too little to learn from — MIN_OBSERVATIONS is 3. A profile
    that has seen this typography before supplies what the volume cannot."""
    thin = document_evidence(_one_page(), threshold=100)
    assert not thin.informed(2)

    corpus = prof.learn([("z.txt", "[x] p. 1  fn 2  cand 1  'z'  conf 0.9  ctx: x\n" * 1)])
    informed = document_evidence(_one_page(), threshold=100, profile=corpus)
    assert informed.informed(2)
    assert informed.share(2, "z") > 0.5


def test_the_profile_reaches_the_rendered_output():
    corpus = prof.learn([("z.txt", "[x] p. 1  fn 2  cand 1  'z'  conf 0.9  ctx: x")])
    ev = document_evidence(_one_page(), 100, profile=corpus)
    out, _audit = render_book(_one_page(), 100, "md", evidence=ev)
    plain, _audit2 = render_book(_one_page(), 100, "md", evidence=NO_EVIDENCE)
    # The body is untouched either way — evidence only ranks and weights.
    assert out == plain
