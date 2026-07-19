"""R3/R4 measurement category (precision before recall, ANFORDERUNG §6)."""
from scriptor.eval.adapters import parse_prepared
from scriptor.eval.citations import evaluate_citations
from scriptor.eval.ground_truth import loads_truth

TRUTH = loads_truth("""
volume = "t"
pages = ["12"]
[[citations]]
page = "12"
text = "Aerts 2003"
regime = "r3"
resolves_to = "aerts2003"
[[citations]]
page = "12"
text = "Dio Chrys., Or. 36.16"
regime = "r4"
[[citations]]
page = "12"
text = "im Jahr 1954"
regime = "none"
[[bibliography]]
key = "aerts2003"
raw = "Aerts 2003. Title."
""")


def test_not_emitted():
    res = evaluate_citations(TRUTH, parse_prepared("[p. 12] Plain text.\n"))
    assert res.emitted is False and res.r3_precision is None


def test_full_marks():
    out = ("[p. 12] See [Aerts 2003]{.cit type=r3 ref=aerts2003} and "
           "[Dio Chrys., Or. 36.16]{.cit type=r4} here.\n")
    res = evaluate_citations(TRUTH, parse_prepared(out))
    assert res.emitted and res.r3_precision == 1.0 and res.r3_recall == 1.0
    assert res.resolution_accuracy == 1.0 and res.r4_recall == 1.0
    assert res.false_positives_on_negatives == 0


def test_event_date_marked_is_a_false_positive():
    out = "[p. 12] Es geschah [im Jahr 1954]{.cit type=r3} wirklich.\n"
    res = evaluate_citations(TRUTH, parse_prepared(out))
    assert res.false_positives_on_negatives == 1
    assert res.r3_precision == 0.0


def test_r4_confused_as_r3_is_counted():
    out = "[p. 12] Vgl. [Dio Chrys., Or. 36.16]{.cit type=r3} dort.\n"
    res = evaluate_citations(TRUTH, parse_prepared(out))
    assert res.r4_confused_as_r3 == 1
