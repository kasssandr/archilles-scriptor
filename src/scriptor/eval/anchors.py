"""Anchor-correctness metric. See the decision logic in the S2 plan (and the
statuses in eval docs): flagged is success, silent misanchoring is damage."""
from __future__ import annotations

from dataclasses import dataclass

from scriptor.eval.adapters import DocFootnote, ParsedDoc, page_at
from scriptor.eval.ground_truth import GroundTruth, TruthFootnote
from scriptor.eval.normalize import find_snippet, normalize

ANCHOR_TOLERANCE = 24   # chars between anchor_after snippet end and the anchor


@dataclass
class NoteOutcome:
    truth: TruthFootnote
    status: str


@dataclass
class AnchorResult:
    outcomes: list[NoteOutcome]
    anchor_rate: float
    handled_rate: float
    silent_damage_rate: float


def _find_definition(doc: ParsedDoc, truth: TruthFootnote) -> DocFootnote | None:
    """The note in the output this truth entry speaks about.

    A snippet is a search key, not an identity. A volume may print the same
    reference twice on one page -- Themistios p. 163 sets "Amm. 26,6,18." as
    note 5 and again as note 6 -- and then the opening text cannot tell them
    apart no matter how much of it is copied. Where several definitions match,
    the anchor decides: the note meant here is the one whose marker sits just
    behind `anchor_after`. Returning the first match instead would score one
    of the twins as misanchored against a converter that placed both right.
    """
    prefix = normalize(truth.definition_starts)
    candidates = [
        fn for fn in doc.footnotes if normalize(fn.definition).startswith(prefix)
    ]
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    if truth.anchor_after:
        span = find_snippet(doc.body, truth.anchor_after)
        if span is not None:
            anchored = [fn for fn in candidates if fn.anchor_offset is not None]
            if anchored:
                # Behind the snippet beats in front of it, then proximity: a
                # marker before its own anchor text belongs to another note.
                return min(
                    anchored,
                    key=lambda fn: (fn.anchor_offset < span[1],
                                    abs(fn.anchor_offset - span[1])),
                )
    return candidates[0]


def _status(doc: ParsedDoc, t: TruthFootnote) -> str:
    fn = _find_definition(doc, t)
    in_body = fn is None and find_snippet(doc.body, t.definition_starts) is not None
    if fn is None and not in_body:
        return "lost"
    for flag in doc.flags:
        if flag.fn_num == t.num and page_at(doc, flag.offset) == t.page:
            return "flagged"
    if fn is None or fn.anchor_offset is None:
        return "preserved_unanchored"
    if page_at(doc, fn.anchor_offset) != t.page:
        return "misanchored"
    if t.anchor_after:
        span = find_snippet(doc.body, t.anchor_after)
        if span is not None:
            gap = fn.anchor_offset - span[1]
            return "anchored_exact" if 0 <= gap <= ANCHOR_TOLERANCE else "misanchored"
    return "anchored_page"


def evaluate_anchors(truth: GroundTruth, doc: ParsedDoc) -> AnchorResult:
    outcomes = [NoteOutcome(t, _status(doc, t)) for t in truth.footnotes]
    total = len(outcomes)
    count = lambda *s: sum(1 for o in outcomes if o.status in s)
    if total == 0:
        return AnchorResult(outcomes, 0.0, 0.0, 0.0)
    anchored = count("anchored_exact", "anchored_page")
    return AnchorResult(
        outcomes,
        anchor_rate=anchored / total,
        handled_rate=(anchored + count("flagged")) / total,
        silent_damage_rate=count("misanchored", "lost") / total,
    )
