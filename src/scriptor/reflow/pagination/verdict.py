"""The verdict: what the witnesses, taken together, say each page is called.

Two things are settled here that the plan deliberately does not settle.

*Which string a page carries.* The plan reasons in ordinals; the label is the
page's identity and travels verbatim from whoever observed it. Re-encoding an
ordinal would turn "XIV" into "14" and send a table-of-contents link into the
front matter.

*Where a segment may be written back.* A segment reaches from its start to the
next one, but reaching a page is not the same as knowing what it is called.
Between the first and the last observation of a segment a page is enclosed --
13 between a printed 12 and a printed 14 is not guessed, it is the only value
left. Past the last observation nothing encloses it. Before the first one the
sequence still has a floor at page 1, and that floor is the anchor the back edge
lacks. Hence: interior yes, front edge yes down to 1, back edge never.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scriptor.reflow.pagelabel import ordinal_of, style_of
from scriptor.reflow.pagination.observation import Observation
from scriptor.reflow.pagination.plan import FitParams, PaginationPlan, fit
from scriptor.reflow.pagination.witnesses import (
    boundary_candidates,
    catalogue_observations,
    catalogue_weight,
    printed_observations,
    toc_observations,
)

# A page in a segment carried by forty printed labels is better attested than
# one in a segment carried by two. Below this many attested positions the
# support grows linearly; a short segment is measured against a fifth of its own
# length, so that being short is not itself held against it.
MIN_SUPPORT_POSITIONS = 8
SUPPORT_FRACTION = 0.2

# How fast confidence falls off with distance from the nearest printed label.
# Deliberately gentle: 181 of 190 interior gaps across the sixteen corpus
# volumes close exactly, so an enclosed page is nearly always right, and a steep
# decay would talk down a reliability that has been measured. The decay exists
# so a derived label is never quite as sure as a printed one -- not to declare
# it doubtful.
DISTANCE_DECAY = 0.95


@dataclass
class Verdict:
    plan: PaginationPlan
    description: str                    # printed to stderr, as before
    rejected: list[Observation] = field(default_factory=list)
    computed_count: int = 0


def _agrees(obs: Observation, plan: PaginationPlan) -> bool:
    seg = plan.segment_at(obs.pos)
    if seg is None or seg.kind == "uncounted":
        return False
    return (style_of(obs.label) == seg.style
            and ordinal_of(obs.label) == plan.value_at(obs.pos))


def run_verdict(pages, params: FitParams | None = None,
                chapters=()) -> Verdict:
    """Set every page's label, its source and its confidence. Say what won.

    ``chapters`` are the confirmed chapter openings (``reflow.chapters``). They
    say nothing about what a page is called -- they say where the volume is
    entitled to change its mind, which is what a boundary candidate is.
    """
    params = params or FitParams()
    for p in pages:
        p.num, p.label, p.label_source, p.label_confidence = -1, None, None, None
    if not pages:
        return Verdict(PaginationPlan(), "none")

    # Where a page states no physical index -- hand-built pages, the bare TXT
    # path -- its place in the list is the only ordering there is. Ordering by
    # it is sound: it is what decides which edge the volume paginates at, and
    # which catalogue reading a page confirms. Reading it as a physical
    # *distance* is not sound, because nothing says the list is complete, so
    # such a document gets only labels somebody observed. Nothing is enclosed
    # where the distance between two pages is unknown.
    stated = {id(p): p.index for p in pages if p.index >= 1}
    if stated:
        pos_of, may_compute = (lambda p: p.index), True
    else:
        fallback = {id(p): i for i, p in enumerate(pages, start=1)}
        pos_of, may_compute = (lambda p: fallback[id(p)]), False

    cat_weight = catalogue_weight(pages, pos_of)
    observations = (printed_observations(pages, pos_of)
                    + catalogue_observations(pages, cat_weight, pos_of)
                    + toc_observations(chapters))
    last_pos = max(pos_of(p) for p in pages)
    plan = fit(observations,
               boundary_candidates(pages, observations, pos_of, chapters),
               last_pos, params)

    at: dict[int, list[Observation]] = {}
    for o in observations:
        at.setdefault(o.pos, []).append(o)
    confirming = {pos: [o for o in group if _agrees(o, plan)]
                  for pos, group in at.items()}

    # Per segment: the first and last position an observation confirms, and the
    # positions a *printed* one confirms -- the latter is what attests a segment
    # and what distance is measured against. A catalogue cannot attest itself.
    spans: dict[int, tuple[int, int]] = {}
    attested: dict[int, list[int]] = {}
    for pos, group in confirming.items():
        seg = plan.segment_at(pos)
        if seg is None or not group:
            continue
        lo, hi = spans.get(seg.start_pos, (pos, pos))
        spans[seg.start_pos] = (min(lo, pos), max(hi, pos))
        if any(o.source.startswith("printed") for o in group):
            attested.setdefault(seg.start_pos, []).append(pos)

    # The floor at page 1 belongs to the first segment the volume *counts*. An
    # uncounted stretch before it -- plates, an unnumbered half-title -- does not
    # move where counting begins, and taking the first segment of any kind here
    # cost Themistios its page 1: the fifteen roman pages before its arabic run
    # come out uncounted, and the run's own head was then never reached.
    first_start = next((s.start_pos for s in plan.segments
                        if s.kind == "counted"), None)
    verdict = Verdict(plan=plan, description="none")

    for p in pages:
        pos = pos_of(p)
        seg = plan.segment_at(pos)
        if seg is None or seg.kind == "uncounted":
            continue
        group = confirming.get(pos, [])
        printed = [o for o in group if o.source.startswith("printed")]
        if printed:
            p.label, p.label_source = printed[0].label, "printed"
        elif group:
            # Which source, not merely "not printed". Masones has no PDF
            # catalogue whatsoever and six of its pages were recorded as
            # "catalogue" -- their labels come from its table of contents. The
            # field travels to archilles, which reads it to know how far a
            # citation can be trusted, so it has to name the witness it had.
            best = min(group, key=lambda o: 0 if o.source == "catalogue" else 1)
            p.label = best.label
            p.label_source = "catalogue" if best.source == "catalogue" else best.source
        else:
            span = spans.get(seg.start_pos)
            if span is None:
                continue
            if not may_compute:
                continue
            lo, hi = span
            enclosed = lo <= pos <= hi
            # Counting backwards is allowed only where the run actually lands on
            # page 1. The floor is the whole justification for treating the
            # front edge differently from the back, and "the value stays above
            # zero" is not the same thing: at L'Empire a year misread as a folio
            # ("1972" on the imprint page) had the first three pages of the
            # volume counted back as 1968, 1969, 1970, and at La masonería an
            # arabic run reached back across a roman front matter. Requiring the
            # run to reach the floor exactly is what the older chain achieved by
            # starting from the volume's first label and stopping at 1.
            front = (pos < lo and seg.start_pos == first_start
                     and plan.value_at(seg.start_pos) == 1)
            if not (enclosed or front):
                continue
            computed = plan.label_of(pos)
            if computed is None:
                continue
            p.label, p.label_source = computed, "computed"
            verdict.computed_count += 1
        p.num = ordinal_of(p.label) or -1
        p.label_confidence = _confidence(pos, seg.start_pos, group,
                                         at.get(pos, []), spans, attested)

    # Rejected: an observation the plan contradicts, at a position where nothing
    # else confirms. Where something does confirm, the other statement is the
    # losing edge of the same page, not a finding -- reporting a running head on
    # every page of the volume would bury what matters.
    verdict.rejected = [
        o for pos, group in sorted(at.items()) for o in group
        if not confirming.get(pos) and not _agrees(o, plan)
    ]
    verdict.description = _describe(pages, confirming, cat_weight)
    return verdict


def _confidence(pos, seg_start, group, all_at_pos, spans, attested) -> float:
    marks = attested.get(seg_start, [])
    if not marks:
        return 0.0
    lo, hi = spans[seg_start]
    support = min(1.0, len(marks) / max(MIN_SUPPORT_POSITIONS,
                                        SUPPORT_FRACTION * (hi - lo + 1)))
    contra = sum(o.weight for o in all_at_pos if o not in group)
    if group:
        agree = sum(o.weight for o in group)
        return (agree / (agree + contra)) * support
    distance = min(abs(pos - m) for m in marks)
    return support * (DISTANCE_DECAY ** distance) / (1.0 + contra)


def _describe(pages, confirming, cat_weight) -> str:
    """The one-line summary printed to stderr, in the older chain's vocabulary.

    "top" / "bottom" name the edge the volume paginates at, which is now a
    consequence of the fit rather than a decision taken before it. The catalogue
    is only named where it actually settled a page -- saying "backend catalogue"
    because a catalogue merely exists would credit it with work it did not do.
    """
    if not any(p.label for p in pages):
        return "none"
    counts: dict[str, int] = {}
    for group in confirming.values():
        for o in group:
            counts[o.source] = counts.get(o.source, 0) + 1
    edges = {e: counts.get(f"printed-{e}", 0) for e in ("bottom", "top")}
    edge = max(("bottom", "top"), key=lambda e: edges[e]) if any(
        edges.values()) else "none"
    settled = sum(1 for p in pages if p.label_source == "catalogue")
    if settled:
        return (f"backend catalogue (agrees with {edge}, settles {settled} "
                f"pages, weight {cat_weight:.2f})")
    return edge
