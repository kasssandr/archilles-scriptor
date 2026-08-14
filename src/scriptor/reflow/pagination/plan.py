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

from scriptor.reflow.pagelabel import encode_label, ordinal_of, style_of

# Numbering systems whose unobserved positions may be written back.
#
# Arabic only, until 2026-08-14. The restraint rested on two grounds and both
# have since been answered. The first was that an arabic label is its own
# ordinal written out while roman needed an encoder -- ``encode_label`` is that
# encoder. The second was that no corpus volume showed an interior roman gap, so
# there was nothing to verify a rule against: La masonería shows 21 of them,
# enclosed between the 43 versal folios the second reading takes off its front
# matter.
#
# What the restraint was right about is still true and is now carried elsewhere:
# the front matter is where an unprinted page may genuinely be uncounted -- a
# plate, a blank verso -- so a roman stretch has to earn its extrapolation the
# same way an arabic one does, by being enclosed between observations
# (``verdict``) and by resting on more than one of them (``min_attested``).
EXTRAPOLATED_STYLES = ("arabic", "roman-lower", "roman-upper")


@dataclass(frozen=True)
class Segment:
    start_pos: int          # positional index this segment takes over at
    # The label at ``start_pos``. Written as an arabic numeral even for a roman
    # segment: it carries the ordinal, which ``ordinal_of`` reads back, while
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
        start = ordinal_of(seg.start_label)
        return None if start is None else start + (pos - seg.start_pos)

    def label_of(self, pos: int) -> str | None:
        """The label the plan writes back for ``pos``, or None.

        Written in the segment's own numbering system (see EXTRAPOLATED_STYLES),
        which is why a versal stretch yields "XIV" and not "xiv". This concerns
        *unobserved* positions only: a page that printed its own label keeps it
        verbatim, and the verdict never asks this method for those.
        """
        seg = self.segment_at(pos)
        if seg is None or seg.style not in EXTRAPOLATED_STYLES:
            return None
        value = self.value_at(pos)
        return None if value is None else encode_label(value, seg.style)


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

    Swept over the sixteen corpus volumes: every combination with mu in
    [1.5, 3.0] and lam in [1.5, 2.5] gives the identical result -- 2481 labels
    over 38 segments -- so the values below sit in the middle of a plateau
    rather than on a slope. The result only changes once lam reaches about twice
    the threshold (lam = 4.0), where it falls to 26 segments and *rises* to 2622
    labels: with boundaries priced out, stretches merge and the fit extrapolates
    across a jump it should have modelled. More labels is the wrong direction
    there, which is why the sweep is read against segment count and not against
    label count alone.
    """

    mu: float = 2.0      # weight of a contradiction
    lam: float = 2.0     # price of one additional segment; > (1+mu)/2 = 1.5
    rho: float = 0.0     # recto bonus; measured per volume, unused for now

    # How many *positions* have to agree before a stretch may be called counted.
    #
    # The segment price protects a running count from being cut up, but it does
    # not protect a stretch nobody can read: there the choice is between an
    # uncounted segment and a counted one, both cost lam, and the counted one is
    # ahead by one confirmation plus the contradiction it avoids. So a single
    # reading at the front of a volume always founds a segment, whatever lam is.
    #
    # Measured over the sixteen corpus volumes: seven of thirty counted segments
    # rested on one observation. Each wrote exactly one label -- its own, filling
    # no gap -- and each of those seven was wrong: imprint years (A comemoração
    # "2020", L'Empire "1972"), a chapter number in a running head (Gli Actus "5"
    # on a page between printed 177 and 180), OCR artefacts (Les apologistes read
    # "li" twice, ninety-six pages apart). The smallest segment that was right
    # had two: Carlomagno's closing pages. Hence two, and hence positions rather
    # than observations -- both edges of one page are one page.
    min_attested: int = 2

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
            if style_of(o.label) == seg.style and ordinal_of(o.label) == predicted
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
    evidence is thin.

    It does not, however, keep a lone misreading from founding a segment: there
    the counted option pays the same segment price and is ahead by the very
    confirmation the misreading provides. That is what ``min_attested`` is for,
    and it is why a stretch offering a single reading now does come out
    uncounted.
    """
    total = 0.0
    for pos, group in _by_position(observations).items():
        if start_pos <= pos < stop_pos:
            total -= params.mu * max(o.weight for o in group)
    return total


# Scoring one candidate offset against a stretch, position by position, is the
# obvious way and it is too slow: the work is candidates * positions * boundary
# pairs, and a volume whose pagination is hard to read produces the most
# candidates -- 200 boundary candidates over 400 pages took 12 seconds.
#
# The identity below removes the "candidates" factor. Writing maxw(p) for the
# heaviest observation at position p and agree(p, o) for the heaviest one there
# voting for offset o:
#
#     score(o) = SUM  [ agree(p, o)  if p agrees, else -mu * maxw(p) ]
#              = -mu * SUM maxw(p)  +  SUM       [ agree(p, o) + mu * maxw(p) ]
#                                       p agrees
#              = score_uncounted     +  gain(o)
#
# So a single pass over the observations accumulates ``gain`` for every offset
# at once, and the same pass extended position by position serves every stretch
# that starts at the same place. That is what ``_Tally`` is for.


class _Tally:
    """Running score of every candidate offset over a growing stretch."""

    def __init__(self, params: FitParams) -> None:
        self.params = params
        self.base = 0.0                              # the uncounted score
        self.gain: dict[tuple[str, int], float] = {}  # (style, offset) -> gain
        self.hits: dict[tuple[str, int], int] = {}    # ... -> positions agreeing

    def add(self, group) -> None:
        """Fold in one position's observations."""
        maxw = max(o.weight for o in group)
        self.base -= self.params.mu * maxw
        agree: dict[tuple[str, int], float] = {}
        for o in group:
            style, value = style_of(o.label), ordinal_of(o.label)
            if style is None or value is None:
                continue
            key = (style, value - o.pos)
            agree[key] = max(agree.get(key, 0.0), o.weight)
        for key, weight in agree.items():
            self.gain[key] = self.gain.get(key, 0.0) + weight + self.params.mu * maxw
            # One per position, not one per observation: ``agree`` is already a
            # dict, so a page whose two edges print the same number counts once.
            self.hits[key] = self.hits.get(key, 0) + 1

    def best(self, start_pos: int) -> tuple[Segment | None, float]:
        """The best counted segment starting at ``start_pos``, and its score.

        Ties go to the smaller offset, then to the alphabetically first style,
        so the result never depends on dict ordering.
        """
        best_seg: Segment | None = None
        best_score = float("-inf")
        for (style, offset) in sorted(self.gain, key=lambda k: (k[1], k[0])):
            start_value = offset + start_pos
            # No volume counts backwards past its own first page.
            if start_value < 1:
                continue
            # Nor does one reading make a numbering system (FitParams.min_attested).
            if self.hits[(style, offset)] < self.params.min_attested:
                continue
            score = self.base + self.gain[(style, offset)]
            if score > best_score:
                best_seg = Segment(start_pos=start_pos,
                                   start_label=str(start_value), style=style)
                best_score = score
        return (best_seg, best_score) if best_seg is not None else (None, 0.0)


def best_segment(observations, start_pos: int, stop_pos: int,
                 params: FitParams) -> tuple[Segment | None, float]:
    """The counted segment that best explains ``[start_pos, stop_pos)``.

    Candidate offsets are not searched, they are read off the observations: an
    observation at ``pos`` claiming ordinal ``n`` votes for the offset
    ``n - pos``.

    The best segment is returned even where its score is negative. Whether a
    stretch is better left uncounted is the caller's comparison to make, and
    withholding the option here would decide it silently. Returns None where no
    offset reaches ``params.min_attested`` -- that is not a comparison but a
    question of standing: one reading is not a numbering system, so there is
    nothing here for the caller to weigh.
    """
    tally = _Tally(params)
    for pos, group in sorted(_by_position(observations).items()):
        if start_pos <= pos < stop_pos:
            tally.add(group)
    return tally.best(start_pos)


def _better(a, b) -> bool:
    """Higher score wins; on a tie, fewer segments; then the lower first start.

    Written out rather than left to tuple comparison, because the first key
    sorts descending and the second ascending. Ties are common enough to matter:
    an isolated misreading and the truth can score alike, and then this decides.
    """
    if a[0] != b[0]:
        return a[0] > b[0]
    if a[1] != b[1]:
        return a[1] < b[1]
    return (a[2][0].start_pos, a[2][0].style, a[2][0].start_label) < (
        b[2][0].start_pos, b[2][0].style, b[2][0].start_label
    )


def fit(observations, boundaries, last_pos: int,
        params: FitParams) -> PaginationPlan:
    """The plan that best explains the observations, over the given boundaries.

    Only positions listed in ``boundaries`` may start a segment. Keeping that
    list short is what keeps the fit fast and, more importantly, readable: a
    boundary is proposed where a printed observation breaks the running count,
    where the catalogue changes its numbering, and where a volume would have
    started counting from 1 -- a few dozen candidates over a whole volume, not
    hundreds. Every extra candidate is one more place for a misreading to hide a
    segment of its own.

    Straight dynamic programming over those candidates. For a fixed segment
    start the tally is carried forward as the stretch grows, so all stretches
    beginning at the same boundary are scored in one pass over the volume rather
    than one pass each.
    """
    bounds = sorted({b for b in boundaries if 1 <= b <= last_pos} or {1})
    by_pos = sorted(_by_position(observations).items())

    # best[i] = (score, segment count, segments) for everything from bounds[i]
    # to the end of the volume. Filled from the back.
    best: list[tuple[float, int, tuple[Segment, ...]]] = [
        (0.0, 0, ()) for _ in bounds
    ]

    for i in range(len(bounds) - 1, -1, -1):
        start = bounds[i]
        choice: tuple[float, int, tuple[Segment, ...]] | None = None
        tally = _Tally(params)
        fed = 0  # how far into by_pos the tally has been carried
        # j is the boundary this segment runs up to; j == len(bounds) means it
        # runs to the end of the volume.
        for j in range(i + 1, len(bounds) + 1):
            stop = bounds[j] if j < len(bounds) else last_pos + 1
            while fed < len(by_pos) and by_pos[fed][0] < stop:
                pos, group = by_pos[fed]
                if pos >= start:
                    tally.add(group)
                fed += 1
            tail_score, tail_count, tail_segs = (
                best[j] if j < len(bounds) else (0.0, 0, ())
            )
            options: list[tuple[Segment, float]] = [(
                Segment(start, "1", "arabic", kind="uncounted"), tally.base,
            )]
            counted, counted_score = tally.best(start)
            if counted is not None:
                options.append((counted, counted_score))
            for seg, seg_score in options:
                # One junction, one segment price. Charging lam per segment
                # still to come makes the penalty grow as lam*k*(k-1)/2 instead
                # of lam*(k-1), so the later boundaries of a volume with several
                # jumps become unaffordable -- and the fit then pays for it by
                # overruling printed labels.
                junction = params.lam if j < len(bounds) else 0.0
                score = seg_score + tail_score - junction
                cand = (score, tail_count + 1, (seg,) + tail_segs)
                if choice is None or _better(cand, choice):
                    choice = cand
        best[i] = choice if choice is not None else (0.0, 0, ())

    return PaginationPlan(segments=best[0][2])
