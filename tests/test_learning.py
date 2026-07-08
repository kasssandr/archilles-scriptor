"""Within-document learning: the glyph a book repeats is a systematic misreading.

A volume is scanned once, in one typeface, by one engine. Whatever it makes of a
superscript 2, it makes of every superscript 2. Counting the glyphs that stand in
this document's own sequence gaps therefore says more than the flat confusion
table can — and it says it without any state surviving the run, so the pipeline
stays reproducible.

The two guardrails are tested here as hard invariants: evidence may reweight and
rank the candidates the structural rules found, and nothing else.
"""
from collections import Counter

from scriptor.reflow.confidence import (
    BASE_PRIOR,
    MIN_OBSERVATIONS,
    NO_EVIDENCE,
    PRIOR_MAX,
    PRIOR_MIN,
    Candidate,
    GlyphEvidence,
    analyse_paragraph,
    classify,
    collect_evidence,
    find_candidates,
)
from scriptor.reflow.core import Page, document_evidence, render_book

# Footnote 2's marker was misread as the 'z' ending "Werkz"; markers 1 and 3
# survived, so the gap is an interior one. The fourth page also holds a 'Z',
# which is in OCR_CONFUSION[2] as well — a rival candidate the book barely uses.
_PLAIN = "Ein Satz mit Note [1] und dann Werkz und Marke [3] hier."
_DECOY = "Ein Satz mit Note [1] und WerkZ oder Werkz und Marke [3] hier."
_FNS = {1: "erste Note", 2: "zweite Note", 3: "dritte Note"}


def _pages():
    bodies = [_PLAIN, _PLAIN, _PLAIN, _DECOY]
    return [Page(n, [b], dict(_FNS), mode="main") for n, b in enumerate(bodies, 1)]


def _evidence():
    return document_evidence(_pages(), threshold=100)


# --- the evidence object ------------------------------------------------------

def test_evidence_counts_glyphs_per_digit():
    ev = _evidence()
    assert ev.count(2, "z") == 4      # once per page
    assert ev.count(2, "Z") == 1      # only the decoy page
    assert ev.observations(2) == 5


def test_a_digit_the_document_barely_mentions_is_not_believed():
    ev = GlyphEvidence(Counter({(2, "z"): MIN_OBSERVATIONS - 1}))
    assert not ev.informed(2)
    assert ev.prior(2, "z") == (BASE_PRIOR, "glyph-in-table")


def test_an_informed_digit_moves_the_prior_within_its_band():
    ev = _evidence()
    assert ev.informed(2)
    dominant, _ = ev.prior(2, "z")
    rare, _ = ev.prior(2, "Z")
    assert PRIOR_MIN <= rare < BASE_PRIOR < dominant <= PRIOR_MAX


def test_prior_reason_names_the_share_so_the_audit_can_be_read():
    ev = _evidence()
    _score, reason = ev.prior(2, "z")
    assert reason == "glyph-share-80%"


def test_counting_cannot_bootstrap_itself():
    """No glyph can confirm itself into dominance.

    Pass one counts the glyphs that qualify, and which glyphs qualify is settled by
    the confusion table and the marker-position rule — never by evidence. So even
    evidence that is wildly biased towards 'z' yields the same counts as none at
    all. (Were the scorer ever allowed to *drop* a candidate, this would break, and
    that is exactly why it is not.)
    """
    paras = [_PLAIN, _PLAIN, _PLAIN, _DECOY]
    fns = [dict(_FNS) for _ in paras]
    biased = GlyphEvidence(Counter({(2, "z"): 99}))

    counted = collect_evidence(paras, fns)
    under_bias: Counter = Counter()
    for para, f in zip(paras, fns):
        for a in analyse_paragraph(para, f, evidence=biased):
            for c in a.candidates:
                under_bias[(a.fn_num, c.char)] += 1

    assert counted.counts == under_bias == Counter({(2, "z"): 4, (2, "Z"): 1})


# --- guardrail one: the candidate set is fixed by structure, not by evidence --

def test_evidence_never_changes_which_glyphs_qualify():
    ev = _evidence()
    interval = " und WerkZ oder Werkz und "
    plain = {c.char for c in find_candidates(interval, 0, 2, evidence=None)}
    learned = {c.char for c in find_candidates(interval, 0, 2, evidence=ev)}
    assert plain == learned == {"z", "Z"}


def test_evidence_never_creates_a_gap():
    ev = GlyphEvidence(Counter({(2, "z"): 99}))
    # Footnote 2's marker is present, so there is nothing to look for.
    para = "Ein Satz mit [1] und Werkz [2] und [3] hier."
    assert analyse_paragraph(para, dict(_FNS), evidence=ev) == []


def test_evidence_never_removes_a_gap():
    ev = _evidence()
    plain = analyse_paragraph(_DECOY, dict(_FNS))
    learned = analyse_paragraph(_DECOY, dict(_FNS), evidence=ev)
    assert [a.fn_num for a in plain] == [a.fn_num for a in learned] == [2]


# --- guardrail two: dominance needs evidence behind it ------------------------

def test_a_score_gap_alone_does_not_settle_a_choice():
    """Without statistics a lead means only 'better placed'. Old contract."""
    strong = Candidate("z", 0.9, "x", (1, 2))
    weak = Candidate("Z", 0.4, "x", (3, 4))
    assert classify([strong, weak]) == "guessed"


def test_evidence_turns_a_guess_into_a_suggestion():
    ev = _evidence()
    plain = analyse_paragraph(_DECOY, dict(_FNS))[0]
    learned = analyse_paragraph(_DECOY, dict(_FNS), evidence=ev)[0]

    assert plain.confidence_class == "guessed"        # two rivals, nothing to choose by
    assert learned.confidence_class == "suggested"    # the book says 'z', 4 times out of 5
    assert learned.candidates[0].char == "z"
    assert learned.candidates[0].seen == 4
    # The rival is kept, so the human can still overrule the statistics.
    assert {c.char for c in learned.candidates} == {"z", "Z"}


def test_a_split_document_stays_a_guess():
    """Evidence that does not favour one glyph must not manufacture confidence."""
    ev = GlyphEvidence(Counter({(2, "z"): 5, (2, "Z"): 5}))
    ann = analyse_paragraph(_DECOY, dict(_FNS), evidence=ev)[0]
    assert ann.confidence_class == "guessed"


# --- end to end ---------------------------------------------------------------

def test_review_master_carries_one_flag_instead_of_two():
    from scriptor.reflow.confidence import Annotator

    def _flags(evidence):
        ann = Annotator()
        render_book(_pages(), threshold=100, fmt="md", annotator=ann, evidence=evidence)
        return sum(len(a.candidates) if a.confidence_class == "guessed" else 1
                   for a in ann.annotations)

    assert _flags(NO_EVIDENCE) == 5    # three plain gaps + two rivals on the decoy
    assert _flags(_evidence()) == 4    # the decoy's rivalry is settled


def test_render_book_learns_on_its_own_when_no_evidence_is_passed():
    with_auto, _ = render_book(_pages(), threshold=100, fmt="md")
    with_given, _ = render_book(_pages(), threshold=100, fmt="md", evidence=_evidence())
    assert with_auto == with_given


def test_evidence_is_a_pure_function_of_the_pages():
    assert document_evidence(_pages(), 100).counts == document_evidence(_pages(), 100).counts
