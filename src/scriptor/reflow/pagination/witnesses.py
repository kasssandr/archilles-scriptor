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

from scriptor.reflow.pagelabel import ordinal_of, style_of
from scriptor.reflow.pagination.observation import Observation

PRINTED_WEIGHT = 1.0


def _index(page) -> int:
    """Where a page sits, as the document states it.

    Every witness takes ``pos_of`` so a caller can supply an ordering the pages
    themselves do not carry -- hand-built pages and the bare TXT path have no
    physical index. Ordering them by their place in the list is sound; treating
    that place as a physical *distance* is not, and the verdict keeps the two
    apart by refusing to compute labels for such a document.
    """
    return page.index

# A catalogue column needs this many pages where both it and a printed label
# exist before its agreement rate means anything. Two agreements cannot tell a
# real catalogue from a mechanically generated one (physical == printed).
MIN_CATALOGUE_OVERLAP = 3


def printed_observations(pages, pos_of=_index) -> list[Observation]:
    """What the pages themselves print, at either edge.

    Both edges are asked. Which one the volume actually paginates at is not
    decided here, and not decided globally either: a plan can only agree with
    one of them throughout, so the edge falls out of the fit.
    """
    out: list[Observation] = []
    for p in pages:
        if pos_of(p) < 1:
            continue
        for label, edge in ((p.label_bottom, "bottom"), (p.label_top, "top")):
            if label is None or ordinal_of(label) is None:
                continue
            out.append(Observation(
                pos=pos_of(p), label=label, source=f"printed-{edge}",
                weight=PRINTED_WEIGHT,
                why=f"{edge} line of physical page {pos_of(p)}",
            ))
    return out


def catalogue_weight(pages, pos_of=_index) -> float:
    """How much this volume's PDF catalogue has earned, from 0 to 1.

    The rate at which it agrees with the printed pages, over the pages where
    both exist. Below MIN_CATALOGUE_OVERLAP there is nothing to judge and the
    answer is zero -- silence, not doubt.
    """
    both = [
        (p.backend_label, p.label_bottom or p.label_top)
        for p in pages
        if pos_of(p) >= 1 and p.backend_label is not None
        and (p.label_bottom or p.label_top) is not None
    ]
    if len(both) < MIN_CATALOGUE_OVERLAP:
        return 0.0
    agree = sum(1 for b, c in both if b.strip().lower() == c.strip().lower())
    return agree / len(both)


def catalogue_observations(pages, weight: float,
                           pos_of=_index) -> list[Observation]:
    """What the PDF's own PageLabels state, where they have earned a hearing."""
    if weight <= 0.0:
        return []
    return [
        Observation(pos=pos_of(p), label=p.backend_label, source="catalogue",
                    weight=weight, why="PDF PageLabels")
        for p in pages
        if pos_of(p) >= 1 and p.backend_label is not None
        and ordinal_of(p.backend_label) is not None
    ]


# What a table of contents is worth when it names a page. Less than the page's
# own printing, because it has been through two steps the printed label has not:
# a parser that read the contents line, and a search that found the title on a
# page. Either can go wrong where a printed folio cannot. More than nothing,
# because it speaks precisely where the printed edge falls silent -- a chapter
# opening is the page a volume most often sets without a folio.
TOC_WEIGHT = 0.6


def toc_observations(chapters, pos_of=None) -> list[Observation]:
    """What the contents says the chapter openings are called in print.

    Only openings that carry a printed page (``ChapterStart.printed``); an
    outline entry has no such thing and says nothing here.
    """
    out: list[Observation] = []
    for c in chapters:
        if not getattr(c, "printed", None) or ordinal_of(c.printed) is None:
            continue
        out.append(Observation(
            pos=c.pos, label=c.printed, source="toc", weight=TOC_WEIGHT,
            why=f"table of contents lists {c.title!r} at printed page {c.printed}",
        ))
    return out


def _decoded(sequence: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """(pos, ordinal, style) for the entries that are labels at all."""
    out = []
    for pos, label in sequence:
        value, style = ordinal_of(label), style_of(label)
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


def boundary_candidates(pages, observations, pos_of=_index,
                        chapters=()) -> list[int]:
    """Positions at which a segment may begin. Position 1 always may.

    Deliberately short. Every candidate multiplies the work of the fit and --
    worse -- gives a misreading one more place to hide a segment of its own.
    """
    candidates = {1}

    # Where a chapter opens is where a printed count jumps: the printer
    # suppresses the blank facing the opening, or starts a new sheet, and the
    # offset between physical and printed page moves. Carlomagno's PDF drops
    # that blank before every opening, so its offset grows by one each time --
    # and the fit could only explain that with a boundary nobody offered it.
    # Confirmed openings only (``chapters.from_outline``), so this stays the
    # short list it has to be.
    candidates |= {c.pos for c in chapters if c.pos >= 1}

    # Breaks are proposed by whichever edge reads as the more coherent run. Both
    # edges are witnesses, but they are not both boundary *proposers*: a running
    # head carrying a chapter number that never moves breaks the count on every
    # page of the volume, and reading it as a folio would litter the fit with
    # candidates. Which edge is right is still the fit's decision -- this only
    # decides whose breaks are worth looking at.
    edges = {
        "bottom": [(pos_of(p), p.label_bottom) for p in pages
                   if pos_of(p) >= 1 and p.label_bottom is not None],
        "top": [(pos_of(p), p.label_top) for p in pages
                if pos_of(p) >= 1 and p.label_top is not None],
    }
    # Ties go to the bottom, which is where volumes paginate far more often and
    # which the older chain also preferred.
    best_edge = max(("bottom", "top"), key=lambda e: _consistent_steps(edges[e]))
    candidates |= _breaks(edges[best_edge])

    # Where the catalogue changes its numbering. Its values may be wrong and its
    # structure still right: at L'Empire and La masonería the catalogue is silent
    # over the front matter and starts counting at physical page 12 resp. 67,
    # which is precisely where each volume's arabic count begins.
    #
    # Expect little more than that. Of the sixteen corpus volumes six carry
    # PageLabels at all, and all six are mechanical -- the label is the physical
    # page plus a fixed offset (A comemoração -2, Asclepios -1, L'Empire -10,
    # La masonería -66, Bauer -1, Making Martyrs 0). Not one of them knows a
    # numbering change of the volume it describes; what they know is where their
    # own run starts. Bauer in particular has no roman-to-arabic turn to know:
    # it paginates straight through from its first page.
    cat = [(pos_of(p), p.backend_label) for p in pages
           if pos_of(p) >= 1 and p.backend_label is not None]
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
        value = ordinal_of(o.label)
        if value is not None and style_of(o.label) == "arabic":
            start = o.pos - value + 1
            if start >= 1:
                candidates.add(start)

    return sorted(candidates)
