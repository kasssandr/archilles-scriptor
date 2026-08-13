"""The hyphen at the end of a line: a break to undo, or a compound to keep.

The rule is measured (reflow/core.py, KEEP_HYPHEN_BEFORE) but was never tested.
It came to light when a rewrite turned the word boundary ``\\b`` in the pattern
into a literal backspace character: the pattern still compiled, every one of the
783 tests still passed, and "Einzel- und Gesamtwerk" would have silently become
"Einzelund Gesamtwerk" in every German volume of the corpus.
"""

from scriptor.reflow.core import dehyphenate_join, is_hard_hyphen


def test_a_line_break_hyphen_disappears():
    assert is_hard_hyphen("Wor-", "te") is False
    assert dehyphenate_join(["Wor-", "te sind Zeichen."]) == "Worte sind Zeichen."


def test_a_compound_with_an_elided_base_word_keeps_its_hyphen():
    # "Einzel- und Gesamtwerk": the hyphen stands in for the word that follows.
    assert is_hard_hyphen("Einzel-", "und Gesamt") is True
    assert dehyphenate_join(["Einzel- und", "Gesamtwerk"]) == "Einzel- und Gesamtwerk"


def test_every_connecting_word_of_the_rule_holds():
    # A pattern that compiles but matches nothing looks exactly like a pattern
    # that works, so each alternative is asked for by name.
    for word in ("und", "oder", "bis", "sowie", "wie", "als", "zur", "zu",
                 "zum", "noch", "aber"):
        assert is_hard_hyphen("Teil-", f"{word} etwas") is True, word


def test_the_word_must_stand_on_its_own():
    # "under" begins with "und" and is not the connecting word. Without the word
    # boundary the rule would keep the hyphen here too.
    assert is_hard_hyphen("Teil-", "undeutlich") is False
    assert is_hard_hyphen("Teil-", "Wiese") is False


def test_the_rule_does_not_care_about_case():
    assert is_hard_hyphen("Teil-", "Und etwas") is True
