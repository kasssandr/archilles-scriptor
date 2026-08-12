"""Region recall (spec §4.4): was the apparatus a volume prints also named?

The region work so far could only count pages that *were* named. That is a
numerator without a denominator, and the open question -- does the vocabulary
cover enough of the world, or does every new language bring new gaps? -- is
not answerable from it. Ground truth supplies the denominator: a handful of
boundaries per volume, declared for the whole book rather than for the
footnote sample, which carries no apparatus at all.

Three numbers, deliberately not averaged into one:

* **block level** -- was the bibliography seen *at all*? A region found and
  closed early still lets a consumer exclude most of it; a region never
  opened is invisible.
* **page level** -- how much of it was named. `exact` demands the right name,
  `apparatus` only demands *some* apparatus name, because a consumer that
  excludes apparatus is unharmed when an index is called a bibliography.
* **false apparatus** -- body pages a region swallowed. §4.4 calls this the
  expensive direction, and it is reported as page labels rather than a rate:
  one such page is worth reading about, and a rate hides which.

Order comes from the candidate document, never from comparing labels as
numbers: a volume that runs xiv, xv, 1, 2 has no numeric order, and pages
carrying no printed label at all are ordinary.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scriptor.eval.adapters import ParsedDoc, region_at
from scriptor.eval.ground_truth import GroundTruth
from scriptor.reflow.regions import APPARATUS


@dataclass
class RegionBlock:
    """One declared region, measured over the pages the candidate prints."""
    name: str
    from_page: str
    pages: int          # pages the candidate carries inside this block
    named: int          # of those, pages the candidate gives the same name
    as_apparatus: int   # of those, pages it gives any apparatus name


@dataclass
class RegionResult:
    blocks: list[RegionBlock] = field(default_factory=list)
    exact_recall: float = 0.0
    apparatus_recall: float = 0.0
    false_apparatus: list[str] = field(default_factory=list)
    unmatched_boundaries: list[str] = field(default_factory=list)
    unclassified: int = 0

    @property
    def blocks_total(self) -> int:
        return len(self.blocks)

    @property
    def blocks_found(self) -> int:
        return sum(1 for b in self.blocks if b.named)


def evaluate_regions(truth: GroundTruth, doc: ParsedDoc) -> RegionResult:
    if not truth.regions:
        return RegionResult()

    boundaries = {r.from_page: r.name for r in truth.regions}
    blocks = {r.from_page: RegionBlock(r.name, r.from_page, 0, 0, 0)
              for r in truth.regions}

    current: RegionBlock | None = None
    seen: set[str] = set()
    result = RegionResult(blocks=list(blocks.values()))

    for label, offset in doc.page_marks:
        if label in boundaries and label not in seen:
            current = blocks[label]
            seen.add(label)
        got = region_at(doc, offset)
        if current is None:
            # Before the first boundary the truth says nothing. Counting these
            # pages either way would invent a denominator.
            result.unclassified += 1
            continue
        current.pages += 1
        if got == current.name:
            current.named += 1
        if got in APPARATUS:
            if current.name in APPARATUS:
                current.as_apparatus += 1
            else:
                result.false_apparatus.append(label)

    result.unmatched_boundaries = [r.from_page for r in truth.regions
                                   if r.from_page not in seen]

    total = sum(b.pages for b in result.blocks)
    result.exact_recall = (sum(b.named for b in result.blocks) / total
                           if total else 0.0)
    app_total = sum(b.pages for b in result.blocks if b.name in APPARATUS)
    result.apparatus_recall = (
        sum(b.as_apparatus for b in result.blocks if b.name in APPARATUS)
        / app_total if app_total else 0.0
    )
    return result
