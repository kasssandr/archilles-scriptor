"""What a rejected observation actually was.

An observation the winning plan contradicts is a line of the book that looks
like a page number and is not one. Naming what it is instead costs nothing --
the observations fall out of the fit either way -- and it is the difference
between a report a reader can check and a list of positions.

**Nothing downstream acts on this.** The line stays in the body in every case
(``restore_rejected_folios``); the classification is written into the report and
the sidecar so a reader can confirm the verdict without opening the PDF.

The categories are measured, not designed. Over the eighteen corpus volumes the
fit rejects 40 observations, and these are the shapes they take. Two of them
correct the design's own proposal (docs/internal/2026-08-13-quellen-verbund-
design.md §6.3):

*A chapter number is not found through the contents.* The design suggested
matching against a ToC entry whose title is confirmed on the page. On Gli Actus,
the volume it was written for, none of the four positions is a confirmed chapter
opening, so the rule never fires. What identifies them is that they form a run
of their own -- 2, 3, 4, 5 across 130 pages, while the pages count in the
forties.

*The commonest kind was not in the design at all.* Seven of the forty are roman
numerals the extraction cut short: the plan says XXII, the page reads "XXI". A
prefix of the truth is a misreading, not a different page.
"""

from __future__ import annotations

from dataclasses import dataclass

from scriptor.reflow.pagelabel import encode_label, ordinal_of

# A year in an imprint, not a folio. Two conditions, and the second is the one
# that carries: the number has to lie beyond the volume's own extent. A book of
# 504 pages has no page 1972, so the reading cannot be a folio whatever the page
# it sits on -- while the design's "before the main part" does not hold, because
# Les apologistes prints its 2005 on a page the mode assignment calls main.
YEAR_MIN, YEAR_MAX = 1400, 2100

# How large a number may be and still read as a chapter number rather than a
# page. Gli Actus counts to 5, Libros to 2; no corpus volume has more than
# fifty chapters, and beyond that the reading competes with real folios.
MAX_CHAPTER_NUMBER = 50

# How far a rescued number may sit from the note numbers around it and still be
# one of them. Not zero, and measured: the running footer sits at the foot of
# the apparatus, so the number taken out of it is as often the note the page
# *ends* on as one it carries. Militarizing Men rescues "17" from a page whose
# own notes start at 18, "28" from a page carrying 25 to 27, "41" from a page
# carrying 43 and 44. Two covers all of them, and a window this narrow cannot
# swallow a folio: a page numbered within two of its own note numbers is a page
# whose notes number in the hundreds, and there the apparatus and the pagination
# have long since parted company.
NOTE_NEIGHBOURHOOD = 2


@dataclass(frozen=True)
class Rejection:
    """One contradicted observation, with what the plan said instead."""

    observation: object          # the Observation the plan contradicts
    verdict: str                 # category slug, see the module docstring
    predicted: str | None        # what the plan states for that position


def _predicted(plan, pos: int) -> str | None:
    """What the plan states at ``pos``, written in that segment's own system."""
    seg = plan.segment_at(pos)
    value = plan.value_at(pos)
    if seg is None or value is None:
        return None
    return encode_label(value, seg.style)


def _is_year(label: str, extent: int) -> bool:
    return (
        len(label) == 4
        and label.isdigit()
        and YEAR_MIN <= int(label) <= YEAR_MAX
        and int(label) > extent
    )


def _is_truncation(label: str, predicted: str | None) -> bool:
    """Did the extraction cut the volume's own numeral short?

    A proper prefix, and shorter -- "XXI" of "XXII". Compared case-insensitively
    because the two readings come from different rounds and one of them may have
    normalised; what matters is the glyphs that are missing.
    """
    if predicted is None or not label:
        return False
    a, b = label.strip().lower(), predicted.strip().lower()
    return len(a) < len(b) and b.startswith(a)


def _chapter_run(rejected) -> set[int]:
    """Positions whose label belongs to a numbering of the volume's own.

    Singly a bare "2" at the head of a page is unreadable -- it could be a
    folio, a chapter number, a plate number. Together with a "3" a hundred pages
    later and a "4" after that, it is a numbering: it counts far too slowly to
    be pages, and it counts.

    Two are enough (Libros numbers two appendices), but they have to *count*:
    Les apologistes reads "li" twice, ninety-six pages apart, and two of the
    same value are not a series.
    """
    small = [
        o for o in rejected
        if (v := ordinal_of(o.label)) is not None and 1 <= v <= MAX_CHAPTER_NUMBER
    ]
    small.sort(key=lambda o: o.pos)
    run: list = []
    best: list = []
    for o in small:
        value = ordinal_of(o.label)
        if run and value == ordinal_of(run[-1].label) + 1:
            run.append(o)
        else:
            run = [o]
        if len(run) > len(best):
            best = list(run)
    return {o.pos for o in best} if len(best) >= 2 else set()


def classify(rejected, pages_by_pos, plan) -> list[Rejection]:
    """Name what each contradicted observation was, in reading order.

    Reading order because the report is read beside the book, and an internal
    index is invisible in a text editor.
    """
    in_a_run = _chapter_run(rejected)
    extent = max(pages_by_pos, default=0)
    out: list[Rejection] = []

    for o in sorted(rejected, key=lambda o: (o.pos, o.source, o.label)):
        page = pages_by_pos.get(o.pos)
        predicted = _predicted(plan, o.pos)
        notes = _notes_around(pages_by_pos, o.pos)
        out.append(
            Rejection(o, _verdict_for(o, page, predicted, in_a_run, extent, notes),
                      predicted)
        )
    return out


def _notes_around(pages_by_pos, pos: int) -> set[int]:
    """The note numbers this page and its neighbours carry.

    The neighbours are asked because a note runs over the page break and the
    running footer sits below the apparatus: the number rescued from it belongs
    to the page's apparatus without necessarily being one of its own
    definitions.
    """
    numbers: set[int] = set()
    for p in (pages_by_pos.get(pos - 1), pages_by_pos.get(pos),
              pages_by_pos.get(pos + 1)):
        numbers |= set(getattr(p, "footnotes", {}) or {})
    return numbers


def _verdict_for(o, page, predicted: str | None, in_a_run: set[int],
                 extent: int, notes: set[int]) -> str:
    """The category, first matching rule wins.

    Ordered by how much each explains: a contents page explains every reading on
    it, whoever made it, while "unknown" explains nothing and comes last.
    """
    if getattr(page, "mode", None) == "toc":
        return "contents-page"
    if o.source == "toc":
        # Named for the disagreement, not for a culprit. Measured against a
        # hand analysis of Gli Actus (2026-08-15), the contents was the one that
        # was right: it states INDICI on printed page 335, the plan states 336,
        # and the volume prints 335. Five of the remaining seven cases are Les
        # apologistes, whose two-book-pages-to-a-sheet scan the segment model
        # cannot represent at all -- so there, too, the reading is sound and the
        # plan is what cannot follow it.
        return "contents-disagrees"
    if o.source == "catalogue":
        return "catalogue"
    if _is_year(o.label, extent):
        return "year"
    if _is_truncation(o.label, predicted):
        return "truncated-numeral"
    # Only a number the footer rescue produced. That rescue reaches into the
    # apparatus by construction, so a number from it that the plan refuses is a
    # note number. A reading off the head or foot of the page is not from there,
    # and letting the apparatus claim it costs the classification its best case:
    # a chapter opening carries note 1, and Gli Actus opens its chapters with a
    # bare "2".
    value = ordinal_of(o.label)
    if (o.source == "printed-footer" and value is not None
            and any(abs(value - n) <= NOTE_NEIGHBOURHOOD for n in notes)):
        return "footnote-number"
    if o.pos in in_a_run:
        return "chapter-number"
    return "unknown"
