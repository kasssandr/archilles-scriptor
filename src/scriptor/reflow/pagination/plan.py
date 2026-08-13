"""The pagination plan: what a volume's numbering looks like, as a few segments.

A printed volume does not number its pages arbitrarily. It runs a stretch of
roman front matter, then counts arabic from 1, and where a chapter opening
swallows an unprinted blank the count carries on regardless. That is a piecewise
arithmetic sequence -- and it is exactly the model the PDF standard uses for
PageLabels, which is what makes a catalogue comparable to the printed pages
instead of a special case.

Two questions are kept apart on purpose:

``value_at``  what the plan *predicts* -- an ordinal, defined for every position
              of a counted segment. Used to score a witness against the plan.
``label_of``  what the page would *carry* -- a string, and only where writing it
              back is defensible.

Conflating them was the flaw in the older chain: it stored the ordinal and
recovered the label from it, which cannot tell roman "xiv" from arabic "14".
"""

from __future__ import annotations

from dataclasses import dataclass

from scriptor.reflow.pagelabel import decode_label, style_of

# Numbering systems whose unobserved positions may be written back. Arabic only,
# for two reasons pointing the same way: an arabic label is its own ordinal
# written out and needs no encoder, and the roman stretch is the front matter --
# the one place where an unprinted page is as likely to be uncounted (a plate, a
# blank verso) as counted. No corpus volume shows an interior roman gap, so
# there is nothing here to verify a rule against. Lifting this is one line, the
# day a volume shows one.
EXTRAPOLATED_STYLES = ("arabic",)


@dataclass(frozen=True)
class Segment:
    start_pos: int          # positional index this segment takes over at
    # The label at ``start_pos``. Written as an arabic numeral even for a roman
    # segment: it carries the ordinal, which ``decode_label`` reads back, while
    # ``style`` carries the numbering system. What a page is *called* never
    # comes from here -- it comes verbatim from whoever observed it.
    start_label: str
    style: str              # "arabic" | "roman-lower" | "roman-upper"
    kind: str = "counted"   # "counted" | "uncounted"


@dataclass(frozen=True)
class PaginationPlan:
    segments: tuple[Segment, ...] = ()

    def segment_at(self, pos: int) -> Segment | None:
        """The segment governing ``pos``; None before the first one."""
        found = None
        for seg in self.segments:
            if seg.start_pos > pos:
                break
            found = seg
        return found

    def value_at(self, pos: int) -> int | None:
        """The ordinal the plan predicts for ``pos``, or None where it predicts
        nothing (before the first segment, or inside an uncounted one)."""
        seg = self.segment_at(pos)
        if seg is None or seg.kind == "uncounted":
            return None
        start = decode_label(seg.start_label)
        return None if start is None else start + (pos - seg.start_pos)

    def label_of(self, pos: int) -> str | None:
        """The label the plan writes back for ``pos``, or None.

        Only arabic segments are written back (see EXTRAPOLATED_STYLES). This
        concerns *unobserved* positions only: a page that printed its own label
        keeps it verbatim, and the verdict never asks this method for those.
        """
        seg = self.segment_at(pos)
        if seg is None or seg.style not in EXTRAPOLATED_STYLES:
            return None
        value = self.value_at(pos)
        return None if value is None else str(value)


@dataclass(frozen=True)
class FitParams:
    """The weights that decide between competing plans.

    Provisional values; they are fixed against the sixteen corpus volumes and
    the measurement is recorded here. Two invariants hold whatever the
    measurement says, and both are asserted below:

    ``mu > 1``          a contradiction has to outweigh a confirmation, or a
                        plan explaining half the volume would rank equal to one
                        explaining all of it.

    ``lam > (1+mu)/2``  a single misread label must never be able to buy its own
                        segment. Inserting one mid-run costs two extra segments
                        (the singleton and the resumption) and pays back one
                        confirmation plus one avoided contradiction, so the
                        condition is 2*lam > 1 + mu. This is the sharp form of
                        "a segment must cost more than one observation is
                        worth", and it is a knife edge: at equality every
                        misreading ties with the truth and only the tie-break
                        decides.
    """

    mu: float = 2.0      # weight of a contradiction
    lam: float = 2.0     # price of one additional segment; > (1+mu)/2 = 1.5
    rho: float = 0.0     # recto bonus; measured per volume, unused for now

    def __post_init__(self) -> None:
        if self.mu <= 1.0:
            raise ValueError("mu must exceed 1")
        if self.lam <= (1.0 + self.mu) / 2.0:
            raise ValueError(
                "lam must exceed (1+mu)/2, or a misreading buys its own segment"
            )


def _by_position(observations) -> dict[int, list]:
    """Observations grouped by the page they speak about.

    A page speaks with one voice. Both edges are asked on every page, so the
    losing edge would otherwise count as a contradiction on every page of the
    volume, and no counted segment could ever beat an uncounted one.
    """
    grouped: dict[int, list] = {}
    for o in observations:
        grouped.setdefault(o.pos, []).append(o)
    return grouped


def score_segment(observations, seg: Segment, start_pos: int, stop_pos: int,
                  params: FitParams) -> float:
    """How well ``seg`` explains the observations in ``[start_pos, stop_pos)``.

    Per position: the heaviest observation agreeing with the plan pays; if none
    agrees, the heaviest observation there is charged, once.
    """
    plan = PaginationPlan(segments=(seg,))
    total = 0.0
    for pos, group in _by_position(observations).items():
        if not (start_pos <= pos < stop_pos):
            continue
        predicted = plan.value_at(pos)
        agreeing = [
            o for o in group
            if style_of(o.label) == seg.style and decode_label(o.label) == predicted
        ]
        if agreeing:
            total += max(o.weight for o in agreeing)
        else:
            total -= params.mu * max(o.weight for o in group)
    return total


def score_uncounted(observations, start_pos: int, stop_pos: int,
                    params: FitParams) -> float:
    """What it costs to declare ``[start_pos, stop_pos)`` uncounted.

    An uncounted stretch claims the volume does not number these pages. A page
    that prints "12" is numbered, so an observation there contradicts the claim
    exactly as it would contradict a wrong counted segment. Without this an
    uncounted segment would score zero everywhere and beat any counted one whose
    evidence is thin -- and a volume with a single printed label would come out
    with no labels at all.
    """
    total = 0.0
    for pos, group in _by_position(observations).items():
        if start_pos <= pos < stop_pos:
            total -= params.mu * max(o.weight for o in group)
    return total


def best_segment(observations, start_pos: int, stop_pos: int,
                 params: FitParams) -> tuple[Segment | None, float]:
    """The counted segment that best explains ``[start_pos, stop_pos)``.

    Candidate offsets are not searched, they are read off the observations: an
    observation at ``pos`` claiming ordinal ``n`` votes for the offset
    ``n - pos``. Ties go to the smaller offset, then to the alphabetically first
    style, so the result never depends on iteration order.

    The best segment is returned even where its score is negative. Whether a
    stretch is better left uncounted is the caller's comparison to make, and
    withholding the option here would decide it silently.
    """
    inside = [o for o in observations if start_pos <= o.pos < stop_pos]
    candidates: set[tuple[str, int]] = set()
    for o in inside:
        style, value = style_of(o.label), decode_label(o.label)
        if style is not None and value is not None:
            candidates.add((style, value - o.pos))

    best_seg: Segment | None = None
    best_score = float("-inf")
    for style, offset in sorted(candidates, key=lambda c: (c[1], c[0])):
        start_value = offset + start_pos
        # No volume counts backwards past its own first page.
        if start_value < 1:
            continue
        seg = Segment(start_pos=start_pos, start_label=str(start_value),
                      style=style)
        score = score_segment(inside, seg, start_pos, stop_pos, params)
        if score > best_score:
            best_seg, best_score = seg, score
    return (best_seg, best_score) if best_seg is not None else (None, 0.0)
