from scriptor.reflow.confidence import (
    Candidate,
    FootnoteAnnotation,
    OCR_CONFUSION,
    T_DEFAULT,
    score_candidate,
    find_candidates,
    classify,
    annotate_paragraph,
    Annotator,
)


def test_score_glued_before_space_is_high():
    score, reason = score_candidate("k", " ")
    assert score == 0.9 and "glued-to-word" in reason


def test_score_isolated_is_low():
    score, _ = score_candidate(" ", " ")
    assert score == 0.6  # 0.4 base + 0.2 (right is space); not glued


def test_score_before_closing_punct():
    score, reason = score_candidate("k", ".")
    assert score == 0.9 and "before-punct/space" in reason


def test_find_candidates_locates_table_glyph():
    # "&" is in OCR_CONFUSION[6]; appears once, glued to "Werk".
    cands = find_candidates("dann Werk& mehr", 0, 6)
    assert len(cands) == 1
    assert cands[0].char == "&"
    assert cands[0].span == (9, 10)
    assert cands[0].confidence == 0.9


def test_find_candidates_empty_when_no_glyph():
    assert find_candidates("ganz harmlos hier", 0, 6) == []


def test_classify_three_classes():
    strong = Candidate("&", 0.9, "x", (1, 2))
    weak = Candidate("b", 0.4, "x", (3, 4))
    assert classify([strong]) == "vorgeschlagen"
    assert classify([weak]) == "geraten"
    assert classify([strong, weak]) == "geraten"
    assert classify([]) == "orphan"


def test_dataclasses_have_expected_fields():
    c = Candidate("A", 0.7, "glued", (2, 3))
    a = FootnoteAnnotation(4, 12, "vorgeschlagen", [c])
    assert a.scope == "page" and a.candidates[0].char == "A"


def test_annotate_vorgeschlagen_single_candidate():
    # FN 5,7 present as [5]/[7]; FN 6 unclaimed; "&" (in OCR_CONFUSION[6])
    # is the only candidate in the [5]..[7] interval. NB: avoid words with
    # 'b'/'G' there — they are also OCR_CONFUSION[6] glyphs (e.g. "sieBtens").
    para = "Erstens [5] dann das Werk& und hinten [7] Schluss."
    fns = {5: "fuenf", 6: "sechs", 7: "sieben"}
    out, anns = annotate_paragraph(para, fns)
    assert "Werk&[?FN:6|&]" in out
    assert "[5]" in out and "[7]" in out  # present markers untouched
    assert len(anns) == 1
    assert anns[0].fn_num == 6 and anns[0].klasse == "vorgeschlagen"


def test_annotate_orphan_no_candidate():
    # OCR_CONFUSION[8] = {B, &, ⁸}; this para contains none of them.
    para = "Hier steht nur Prosa ohne Marke."
    out, anns = annotate_paragraph(para, {8: "acht"})
    assert out.endswith("[?FN:8]")
    assert anns[0].klasse == "orphan" and anns[0].candidates == []


def test_annotate_geraten_distributes_flags():
    # Two "b" glyphs (OCR_CONFUSION[6]) -> two candidates -> geraten,
    # one flag per candidate position.
    para = "alpha bravo charlie bingo ende"
    out, anns = annotate_paragraph(para, {6: "sechs"})
    assert anns[0].klasse == "geraten"
    assert out.count("[??FN:6|b:") == 2


def test_annotate_claimed_footnote_gets_no_flag():
    para = "Wort [4] mehr Text."
    out, anns = annotate_paragraph(para, {4: "vier"})
    assert out == para and anns == []


def test_annotator_accumulates():
    a = Annotator()
    a.annotate("Ein Absatz ohne Zeichen.", {2: "zwei"})
    a.annotate("Noch einer ohne Zeichen.", {2: "zwei"})
    assert len(a.annotations) == 2
