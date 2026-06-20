from scriptor.reflow.confidence import (
    Candidate,
    FootnoteAnnotation,
    OCR_CONFUSION,
    T_DEFAULT,
    score_candidate,
    find_candidates,
    classify,
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
