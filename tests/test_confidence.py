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
    render_audit,
)


def test_score_attached_before_space():
    # word-end marker: glued to a letter (+0.3) and a space follows (+0.1).
    score, reason = score_candidate("k", " ")
    assert score == 0.8 and "attached" in reason and "before-space" in reason


def test_score_isolated_is_low():
    score, _ = score_candidate(" ", " ")
    assert score == 0.5  # 0.4 base + 0.1 (right is space); not attached


def test_score_before_closing_punct():
    # attached (+0.3) and a closing/sentence punct follows (+0.2) -> strong.
    score, reason = score_candidate("k", ".")
    assert score == 0.9 and "before-close-punct" in reason


def test_find_candidates_locates_table_glyph():
    # "&" is in OCR_CONFUSION[6]; appears once at a word end (space follows).
    cands = find_candidates("dann Werk& mehr", 0, 6)
    assert len(cands) == 1
    assert cands[0].char == "&"
    assert cands[0].span == (9, 10)
    assert cands[0].confidence == 0.8


def test_find_candidates_empty_when_no_glyph():
    assert find_candidates("ganz harmlos hier", 0, 6) == []


def test_classify_three_classes():
    strong = Candidate("&", 0.9, "x", (1, 2))
    weak = Candidate("b", 0.4, "x", (3, 4))
    assert classify([strong]) == "suggested"
    assert classify([weak]) == "guessed"
    assert classify([strong, weak]) == "guessed"
    assert classify([]) == "orphan"


def test_dataclasses_have_expected_fields():
    c = Candidate("A", 0.7, "glued", (2, 3))
    a = FootnoteAnnotation(4, "12", "suggested", [c])
    assert a.scope == "page" and a.candidates[0].char == "A"


def test_annotate_suggested_single_candidate():
    # FN 5,7 present as [5]/[7]; FN 6 unclaimed; "&" (in OCR_CONFUSION[6])
    # is the only candidate in the [5]..[7] interval. NB: avoid words with
    # 'b'/'G' there — they are also OCR_CONFUSION[6] glyphs (e.g. "sieBtens").
    para = "Erstens [5] dann das Werk& und hinten [7] Schluss."
    fns = {5: "fuenf", 6: "sechs", 7: "sieben"}
    out, anns = annotate_paragraph(para, fns)
    assert "Werk&[?FN:6|&]" in out
    assert "[5]" in out and "[7]" in out  # present markers untouched
    assert len(anns) == 1
    assert anns[0].fn_num == 6 and anns[0].confidence_class == "suggested"


def test_annotate_orphan_no_candidate():
    # FN 8 is an interior gap (bounded by [7] and [9]) but no OCR_CONFUSION[8]
    # glyph ({B, &, ⁸}) sits in the interval -> orphan.
    para = "Hier [7] steht nur Prosa ohne Marke [9] danach."
    out, anns = annotate_paragraph(para, {7: "sieben", 8: "acht", 9: "neun"})
    # The flag stands at the upper bound of the gap, before [9] (spec §4.3).
    assert "[?FN:8][9]" in out
    assert anns[0].confidence_class == "orphan" and anns[0].candidates == []


def test_annotate_guessed_distributes_flags():
    # FN 6 is an interior gap (bounded by [5] and [7]); two "&" glyphs
    # (OCR_CONFUSION[6]) at WORD ENDS in the interval -> two candidates ->
    # guessed, one flag per candidate position.
    para = "Anfang [5] Werk& und Buch& Ende [7] Schluss."
    out, anns = annotate_paragraph(para, {5: "fuenf", 6: "sechs", 7: "sieben"})
    assert anns[0].confidence_class == "guessed"
    assert out.count("[??FN:6|&:") == 2


def test_annotate_claimed_footnote_gets_no_flag():
    para = "Wort [4] mehr Text."
    out, anns = annotate_paragraph(para, {4: "vier"})
    assert out == para and anns == []


def test_annotator_accumulates():
    # FN 2 is an interior gap (bounded by [1] and [3]) in each paragraph, so
    # each call contributes one annotation.
    a = Annotator()
    a.annotate("Vorn [1] der Absatz Zeichen [3] danach.", {1: "x", 2: "y", 3: "z"})
    a.annotate("Auch [1] hier ein Absatz Text [3] Ende.", {1: "x", 2: "y", 3: "z"})
    assert len(a.annotations) == 2


def test_render_audit_has_summary_and_per_flag_lines():
    anns = [
        FootnoteAnnotation(6, "12", "suggested", [Candidate("&", 0.9, "glued", (20, 21))]),
        FootnoteAnnotation(2, "5", "orphan", []),
    ]
    text = render_audit(anns, total_fn_defs=8, page_count=3, out_path="book.md")
    assert "3 pages" in text
    assert "6 certain" in text   # 8 defs - 2 uncertain = 6 certain
    assert "2 uncertain" in text
    assert "p. 12: FN 6 [suggested]" in text
    assert "&:0.9" in text
    assert "p. 5: FN 2 [orphan]" in text
