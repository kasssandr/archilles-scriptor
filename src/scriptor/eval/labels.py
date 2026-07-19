"""Page-label fidelity via sequence alignment of printed labels."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from scriptor.eval.adapters import ParsedDoc
from scriptor.eval.ground_truth import GroundTruth


@dataclass
class LabelResult:
    found: int
    missing: int
    out_of_order: int
    extra: int
    label_fidelity: float


def evaluate_labels(truth: GroundTruth, doc: ParsedDoc) -> LabelResult:
    want = truth.pages
    got = [lbl for lbl, _ in doc.page_marks]
    sm = SequenceMatcher(a=want, b=got, autojunk=False)
    found = sum(size for _, _, size in sm.get_matching_blocks())
    missing = len(want) - found
    extra = len(got) - found
    out_of_order = sum(1 for l in set(want) if l in got) - len(
        {want[i] for block in sm.get_matching_blocks()
         for i in range(block.a, block.a + block.size)}
    )
    total = len(want)
    return LabelResult(found, missing, max(out_of_order, 0), extra,
                       found / total if total else 0.0)
