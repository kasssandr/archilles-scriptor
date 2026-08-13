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
    # Only pages the truth covers. A sampled corpus authors a dozen pages out
    # of hundreds, and about the rest it says nothing -- a flag there is not
    # noise, it is out of scope. Counting it turned Bauer's one flag, on an
    # unauthored page, into a precision of 0.00.
    authored = set(truth.pages)
    cases = {(page_at(doc, f.offset), f.fn_num) for f in doc.flags}
    cases = {c for c in cases if c[0] in authored}
    justified = sum(1 for c in cases if c in damaged)
    noise = len(cases) - justified
    precision = justified / len(cases) if cases else None
    return FlagResult(justified, noise, precision)
