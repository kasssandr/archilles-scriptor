"""R3/R4 citation metric. Precision before recall: one false positive on a
negative example outweighs recall gains (ANFORDERUNG_inline_zitationen §6)."""
from __future__ import annotations

from dataclasses import dataclass

from scriptor.eval.adapters import DocCitSpan, ParsedDoc, page_at
from scriptor.eval.ground_truth import GroundTruth, TruthCitation
from scriptor.eval.normalize import normalize


@dataclass
class CitationResult:
    emitted: bool
    r3_precision: float | None = None
    r3_recall: float | None = None
    resolution_accuracy: float | None = None
    r4_recall: float | None = None
    r4_confused_as_r3: int = 0
    false_positives_on_negatives: int = 0


def _match(doc: ParsedDoc, span: DocCitSpan, t: TruthCitation) -> bool:
    return normalize(span.text) == normalize(t.text) and page_at(doc, span.offset) == t.page


def evaluate_citations(truth: GroundTruth, doc: ParsedDoc) -> CitationResult:
    if not doc.cit_spans:
        return CitationResult(emitted=False)
    r3_truth = [t for t in truth.citations if t.regime == "r3"]
    r4_truth = [t for t in truth.citations if t.regime == "r4"]
    negatives = [t for t in truth.citations if t.regime == "none"]

    r3_spans = [s for s in doc.cit_spans if s.regime == "r3"]
    r4_spans = [s for s in doc.cit_spans if s.regime == "r4"]

    def hits(spans, truths):
        return [(s, t) for s in spans for t in truths if _match(doc, s, t)]

    r3_hits = hits(r3_spans, r3_truth)
    resolved_ok = sum(1 for s, t in r3_hits if s.ref == t.resolves_to)
    matched_r3_truths = {id(t) for _s, t in r3_hits}
    r4_hits = hits(r4_spans, r4_truth)
    matched_r4_truths = {id(t) for _s, t in r4_hits}

    return CitationResult(
        emitted=True,
        r3_precision=len(r3_hits) / len(r3_spans) if r3_spans else None,
        r3_recall=(len(matched_r3_truths) / len(r3_truth)) if r3_truth else None,
        resolution_accuracy=(resolved_ok / len(r3_hits)) if r3_hits else None,
        r4_recall=(len(matched_r4_truths) / len(r4_truth)) if r4_truth else None,
        r4_confused_as_r3=len(hits(r3_spans, r4_truth)),
        false_positives_on_negatives=len(hits(list(doc.cit_spans), negatives)),
    )
