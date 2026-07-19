"""Flag precision: flags are only valuable when they point at real damage."""
from __future__ import annotations

from dataclasses import dataclass

from scriptor.eval.adapters import ParsedDoc, page_at
from scriptor.eval.ground_truth import GroundTruth


@dataclass
class FlagResult:
    justified: int
    noise: int
    flag_precision: float | None


def evaluate_flags(truth: GroundTruth, doc: ParsedDoc) -> FlagResult:
    damaged = {(t.page, t.num) for t in truth.footnotes if t.status != "intact"}
    cases = {(page_at(doc, f.offset), f.fn_num) for f in doc.flags}
    justified = sum(1 for c in cases if c in damaged)
    noise = len(cases) - justified
    precision = justified / len(cases) if cases else None
    return FlagResult(justified, noise, precision)
