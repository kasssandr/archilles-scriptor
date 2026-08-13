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
    # Positions where the tool states a label and the volume states a different
    # one. Distinct from ``missing`` on purpose: a page without a marker costs a
    # citation, a page with the wrong marker costs the reader's trust, because
    # nothing about it looks broken. The source consensus can produce this
    # failure where the older chain could not, so it has to be measured.
    wrong: int
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
    # Aligned position by position: only where both sequences have an entry and
    # the entries differ is something stated falsely. Positions the alignment
    # drops on one side are missing or extra, not wrong.
    wrong = sum(
        min(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in sm.get_opcodes()
        if tag == "replace"
    )
    total = len(want)
    return LabelResult(found, missing, max(out_of_order, 0), extra, wrong,
                       found / total if total else 0.0)
