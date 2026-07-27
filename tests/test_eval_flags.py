"""Flag precision: a flag must point at a genuinely damaged note."""
from scriptor.eval.adapters import parse_prepared
from scriptor.eval.flags import evaluate_flags
from scriptor.eval.ground_truth import loads_truth

TRUTH = loads_truth("""
volume = "t"
pages = ["1"]
[[footnotes]]
page = "1"
num = 2
definition_starts = "Damaged note"
status = "marker_lost"
[[footnotes]]
page = "1"
num = 3
definition_starts = "Fine note"
status = "intact"
""")


def test_justified_and_noise_and_dedup():
    out = ("[p. 1] Text&[?FN:2|&] more&[??FN:2|b:0.7] and a bogus[?FN:3] flag.\n\n"
           "[^1]: Damaged note text.\n")
    res = evaluate_flags(TRUTH, parse_prepared(out))
    # two flags for note 2 collapse to one justified case; note 3 is intact -> noise
    assert (res.justified, res.noise) == (1, 1)
    assert res.flag_precision == 0.5


def test_no_flags_yields_none():
    res = evaluate_flags(TRUTH, parse_prepared("[p. 1] Clean text.\n"))
    assert res.flag_precision is None
