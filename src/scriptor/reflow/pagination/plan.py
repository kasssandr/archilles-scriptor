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

from scriptor.reflow.pagelabel import decode_label

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
