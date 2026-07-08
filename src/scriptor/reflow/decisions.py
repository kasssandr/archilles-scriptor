"""The decision sidecar: which candidate glyph really is the lost footnote marker.

The pipeline is deterministic — no model in the loop — so the same input and the
same code always yield the same candidates. A correction therefore does not need
the rendered Markdown to be read back into the model. (It could not be: the master
records only the document-wide id ``[^3]``, never the page-local footnote it came
from.) What it needs is the *decisions*. Mark a candidate here, run the reflow
again, and the accepted glyph becomes a real marker while every certain decision
is reproduced untouched.

This is an amendment to KONZEPT_scriptor_v2.md §9 Q1: the Markdown master is a
view, not storage. Determinism replaces the round trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# "[x] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: …"
#
# The glyph is written with repr(), so a glyph that is itself an apostrophe — and
# one is, OCR_CONFUSION[4] holds "'" — comes out double-quoted. Accept either.
_LINE_RE = re.compile(
    r"^\[(?P<mark>[ xX])\]\s+p\.\s*(?P<page>\S+)\s+fn\s*(?P<fn>\d+)\s+cand\s*(?P<cand>\d+)"
    r"(?:\s+(?P<q>['\"])(?P<glyph>.)(?P=q))?"
)

# (printed page label, footnote number as printed on that page)
FootnoteRef = tuple[str, int]


class AmbiguousDecision(ValueError):
    """Two candidates marked for the same footnote. Refuse rather than pick one."""


@dataclass(frozen=True)
class DecisionLine:
    """One candidate line, as written in the file."""

    marked: bool
    page: str
    fn: int
    cand: int
    glyph: str | None

    @property
    def ref(self) -> FootnoteRef:
        return (self.page, self.fn)


def read_lines(text: str) -> list[DecisionLine]:
    """Every candidate line of a decision file, marked or not. Lines that do not
    parse are not decisions and are skipped in silence — the file is mostly
    comments."""
    out: list[DecisionLine] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        out.append(
            DecisionLine(
                marked=m.group("mark") != " ",
                page=m.group("page"),
                fn=int(m.group("fn")),
                cand=int(m.group("cand")),
                glyph=m.group("glyph"),
            )
        )
    return out


@dataclass
class Decisions:
    """Accepted candidates, keyed by the footnote they resolve.

    ``accepted[(page, fn)] = candidate_index`` (1-based, as listed in the file).
    """

    accepted: dict[FootnoteRef, int] = field(default_factory=dict)
    applied: list[FootnoteRef] = field(default_factory=list)
    unmatched: list[FootnoteRef] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.accepted)

    def reset_report(self) -> None:
        self.applied.clear()
        self.unmatched.clear()


def parse(text: str) -> Decisions:
    """Read a decision file. Unmarked and unparseable lines are simply not
    decisions; a footnote marked twice is an error, because guessing which mark
    the human meant is exactly the silent misattachment this project avoids."""
    accepted: dict[FootnoteRef, int] = {}
    for line in read_lines(text):
        if not line.marked:
            continue
        if line.ref in accepted and accepted[line.ref] != line.cand:
            raise AmbiguousDecision(
                f"footnote {line.fn} on page {line.page} has two candidates marked "
                f"({accepted[line.ref]} and {line.cand}); mark exactly one"
            )
        accepted[line.ref] = line.cand
    return Decisions(accepted=accepted)


def load(path: str | Path) -> Decisions:
    return parse(Path(path).read_text(encoding="utf-8"))


_HEADER = """\
# Open footnote decisions for {out}
# {count} still open.
#
# A footnote's text survived OCR but the small superscript marker that anchored
# it did not. Below are the glyphs that could be that marker, best first. Put an
# x in the box of the right one and run the reflow again with:
#
#     scriptor reflow <pages> --out {out} --decisions {path}
#
# Leave a box empty to keep the footnote as an unreferenced definition at the end
# of its paragraph — nothing is lost either way, the anchor is simply not claimed.
# Marking two candidates for the same footnote is refused, not guessed.
#
# This file is regenerated on every run and lists only what is still open.
"""


def render_template(annotations, out_path: str, self_path: str) -> str:
    """One line per candidate of every footnote that still has one."""
    lines: list[str] = []
    for a in annotations:
        if not a.candidates or not a.page:
            continue  # no candidate to choose from, or a page we cannot address
        for i, c in enumerate(a.candidates, start=1):
            # "seen" is what this book itself says: how often that glyph stood for
            # that footnote number in a gap. A glyph the volume repeats is a
            # systematic misreading, not a coincidence.
            seen = f"seen {c.seen}x  " if c.seen > 1 else ""
            lines.append(
                f"[ ] p. {a.page}  fn {a.fn_num}  cand {i}  "
                f"{c.char!r}  conf {c.confidence:.1f}  {seen}ctx: {c.context}"
            )
    header = _HEADER.format(out=out_path, path=self_path, count=len(lines))
    return header + "\n" + ("\n".join(lines) + "\n" if lines else "")
