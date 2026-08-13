"""Who says what about a page, and where a segment may begin.

Each witness answers one question, and answers it about a position -- never
about the volume. What the statements add up to is the plan's business
(``plan.fit``).

Weights: a printed label is what the volume itself put on the page, so it
carries full weight. The catalogue carries what it has earned on this volume --
scan tooling generates catalogues mechanically, and believing an unearned one
shifts every citation in the book.
"""

from __future__ import annotations

from scriptor.reflow.pagelabel import decode_label, style_of
from scriptor.reflow.pagination.observation import Observation

PRINTED_WEIGHT = 1.0

# A catalogue column needs this many pages where both it and a printed label
# exist before its agreement rate means anything. Two agreements cannot tell a
# real catalogue from a mechanically generated one (physical == printed).
MIN_CATALOGUE_OVERLAP = 3


def printed_observations(pages) -> list[Observation]:
    """What the pages themselves print, at either edge.

    Both edges are asked. Which one the volume actually paginates at is not
    decided here, and not decided globally either: a plan can only agree with
    one of them throughout, so the edge falls out of the fit.
    """
    out: list[Observation] = []
    for p in pages:
        if p.index < 1:
            continue
        for label, edge in ((p.label_bottom, "bottom"), (p.label_top, "top")):
            if label is None or decode_label(label) is None:
                continue
            out.append(Observation(
                pos=p.index, label=label, source=f"printed-{edge}",
                weight=PRINTED_WEIGHT,
                why=f"{edge} line of physical page {p.index}",
            ))
    return out


def catalogue_weight(pages) -> float:
    """How much this volume's PDF catalogue has earned, from 0 to 1.

    The rate at which it agrees with the printed pages, over the pages where
    both exist. Below MIN_CATALOGUE_OVERLAP there is nothing to judge and the
    answer is zero -- silence, not doubt.
    """
    both = [
        (p.backend_label, p.label_bottom or p.label_top)
        for p in pages
        if p.index >= 1 and p.backend_label is not None
        and (p.label_bottom or p.label_top) is not None
    ]
    if len(both) < MIN_CATALOGUE_OVERLAP:
        return 0.0
    agree = sum(1 for b, c in both if b.strip().lower() == c.strip().lower())
    return agree / len(both)


def catalogue_observations(pages, weight: float) -> list[Observation]:
    """What the PDF's own PageLabels state, where they have earned a hearing."""
    if weight <= 0.0:
        return []
    return [
        Observation(pos=p.index, label=p.backend_label, source="catalogue",
                    weight=weight, why="PDF PageLabels")
        for p in pages
        if p.index >= 1 and p.backend_label is not None
        and decode_label(p.backend_label) is not None
    ]


def _decoded(sequence: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """(pos, ordinal, style) for the entries that are labels at all."""
    out = []
    for pos, label in sequence:
        value, style = decode_label(label), style_of(label)
        if value is not None and style is not None:
            out.append((pos, value, style))
    return out


def _breaks(sequence: list[tuple[int, str]]) -> set[int]:
    """Positions where a run of (pos, label) stops running.

    A break is either a change of numbering system or a step that does not match
    the physical distance -- exactly the two things a new segment explains.
    """
    out: set[int] = set()
    prev = None
    for pos, value, style in _decoded(sequence):
        if prev is not None:
            p_pos, p_value, p_style = prev
            if style != p_style or value - p_value != pos - p_pos:
                out.add(pos)
        prev = (pos, value, style)
    return out


def _consistent_steps(sequence: list[tuple[int, str]]) -> int:
    """How many adjacent steps of this reading run on without a break."""
    steps = 0
    prev = None
    for pos, value, style in _decoded(sequence):
        if prev is not None:
            p_pos, p_value, p_style = prev
            if style == p_style and value - p_value == pos - p_pos:
                steps += 1
        prev = (pos, value, style)
    return steps


def boundary_candidates(pages, observations) -> list[int]:
    """Positions at which a segment may begin. Position 1 always may.

    Deliberately short. Every candidate multiplies the work of the fit and --
    worse -- gives a misreading one more place to hide a segment of its own.
    """
    candidates = {1}

    # Breaks are proposed by whichever edge reads as the more coherent run. Both
    # edges are witnesses, but they are not both boundary *proposers*: a running
    # head carrying a chapter number that never moves breaks the count on every
    # page of the volume, and reading it as a folio would litter the fit with
    # candidates. Which edge is right is still the fit's decision -- this only
    # decides whose breaks are worth looking at.
    edges = {
        "bottom": [(p.index, p.label_bottom) for p in pages
                   if p.index >= 1 and p.label_bottom is not None],
        "top": [(p.index, p.label_top) for p in pages
                if p.index >= 1 and p.label_top is not None],
    }
    # Ties go to the bottom, which is where volumes paginate far more often and
    # which the older chain also preferred.
    best_edge = max(("bottom", "top"), key=lambda e: _consistent_steps(edges[e]))
    candidates |= _breaks(edges[best_edge])

    # Where the catalogue changes its numbering. Its values may be wrong and its
    # structure still right -- Bauer's catalogue is off by one on all 339 pages
    # and knows exactly where the volume turns from roman to arabic.
    cat = [(p.index, p.backend_label) for p in pages
           if p.index >= 1 and p.backend_label is not None]
    candidates |= _breaks(sorted(cat))

    # Where the volume would have started counting from 1, given what a page
    # prints. Bauer prints "7" on its seventh physical page and counts its title
    # pages, so counting starts at position 1; Themistios prints "2" on physical
    # page 17, so it starts at 16 and the roman pages before it are not part of
    # that stretch. Without this candidate such a segment would have to begin
    # where its own value is below 1, which no segment may.
    for o in observations:
        if not o.source.startswith("printed"):
            continue
        value = decode_label(o.label)
        if value is not None and style_of(o.label) == "arabic":
            start = o.pos - value + 1
            if start >= 1:
                candidates.add(start)

    return sorted(candidates)
