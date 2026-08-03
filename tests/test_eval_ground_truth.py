"""truth.toml parsing and validation for the evaluation harness."""
import pytest

from scriptor.eval.ground_truth import TruthError, loads_truth

MINIMAL = """
volume = "demo"
pages = ["iv", "1", "2"]

[[footnotes]]
page = "1"
num = 2
anchor_after = "loses its marker"
definition_starts = "Second note"
status = "marker_lost"

[[citations]]
page = "2"
text = "Aerts 2003"
regime = "r3"
resolves_to = "aerts2003"

[[citations]]
page = "2"
text = "im Jahr 1954"
regime = "none"

[[bibliography]]
key = "aerts2003"
raw = "Aerts, W. J. 2003. Some Title."
"""


def test_minimal_truth_parses():
    t = loads_truth(MINIMAL)
    assert t.volume == "demo"
    assert t.pages == ["iv", "1", "2"]
    fn = t.footnotes[0]
    assert (fn.page, fn.num, fn.status) == ("1", 2, "marker_lost")
    assert fn.anchor_after == "loses its marker"
    assert t.citations[0].resolves_to == "aerts2003"
    assert t.citations[1].regime == "none"
    assert t.bibliography[0].key == "aerts2003"


def test_footnote_defaults_and_optional_anchor():
    t = loads_truth(
        'volume="d"\npages=["1"]\n[[footnotes]]\npage="1"\nnum=1\n'
        'definition_starts="Only note"\nstatus="intact"\n'
    )
    assert t.footnotes[0].anchor_after is None
    assert t.citations == [] and t.bibliography == []


@pytest.mark.parametrize("mutation", [
    'status = "typo"',                    # unknown status
    'page = "99"',                        # page not in pages list
])
def test_invalid_truth_is_refused(mutation):
    bad = MINIMAL.replace('status = "marker_lost"', mutation) if "status" in mutation \
        else MINIMAL.replace('page = "1"\nnum = 2', f'{mutation}\nnum = 2')
    with pytest.raises(TruthError):
        loads_truth(bad)


def test_unknown_regime_is_refused():
    with pytest.raises(TruthError):
        loads_truth(MINIMAL.replace('regime = "r3"', 'regime = "r9"'))


# page-crossing notes -------------------------------------------------------
# A note that breaks off at the foot of one page and resumes on the next is a
# variant nothing in the literature measures. Recording only where it starts
# cannot show whether a converter kept it whole, so the truth carries the end
# of the definition and the page that receives it.

CROSSING = """
volume = "d"
pages = ["88", "89"]

[[footnotes]]
page = "88"
num = 280
definition_starts = "Mit der Wiederbelebung der Antike"
definition_ends = "aetas obscura, für das Mittelalter."
continues_on = "89"
status = "intact"
"""


def test_footnote_records_its_end_and_continuation():
    fn = loads_truth(CROSSING).footnotes[0]
    assert fn.definition_ends == "aetas obscura, für das Mittelalter."
    assert fn.continues_on == "89"


def test_both_fields_are_optional():
    fn = loads_truth(
        'volume="d"\npages=["1"]\n[[footnotes]]\npage="1"\nnum=1\n'
        'definition_starts="A note that stays put"\nstatus="intact"\n'
    ).footnotes[0]
    assert fn.definition_ends is None and fn.continues_on is None


def test_continuation_page_must_be_a_known_page():
    with pytest.raises(TruthError):
        loads_truth(CROSSING.replace('continues_on = "89"', 'continues_on = "99"'))


def test_note_must_not_continue_on_its_own_page():
    with pytest.raises(TruthError):
        loads_truth(CROSSING.replace('continues_on = "89"', 'continues_on = "88"'))
