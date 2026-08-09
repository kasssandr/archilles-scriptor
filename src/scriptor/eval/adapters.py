"""Candidate-output adapters.

parse_prepared() reads spec-conform prepared Markdown (PREPARED_FORMAT_SPEC
v0.1). parse_plain() (Task 4) is the fallback for foreign converter output.
Both produce the same ParsedDoc shape; every metric consumes only that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scriptor.reflow.pagelabel import PAGE_MARKER_RE

# Spec §5 flag grammar. Group 1: sigil (? or ??), 2: printed number,
# 3: candidate glyph (absent on orphan flags).
FLAG_RE = re.compile(r"\[(\?\??)FN:(\d+)(?:\|([^\]:]+)(?::0?\.\d)?)?\]")
# Spec §4.3 / Pandoc: anchors and definitions.
ANCHOR_RE = re.compile(r"\[\^(\d+)\]")
DEF_RE = re.compile(r"^\[\^(\d+)\]:\s*(.*)$", re.MULTILINE)
# Spec §8 citation spans: [text]{.cit type=r3 ref=key}
CIT_RE = re.compile(
    r"\[([^\]]+)\]\{\.cit\s+type=(r[34])(?:\s+ref=([\w:-]+))?\}"
)


@dataclass
class DocFootnote:
    ident: int
    definition: str
    anchor_offset: int | None


@dataclass
class DocFlag:
    fn_num: int
    offset: int
    kind: str


@dataclass
class DocCitSpan:
    text: str
    regime: str
    ref: str | None
    offset: int


@dataclass
class ParsedDoc:
    body: str
    page_marks: list[tuple[str, int]] = field(default_factory=list)
    footnotes: list[DocFootnote] = field(default_factory=list)
    flags: list[DocFlag] = field(default_factory=list)
    cit_spans: list[DocCitSpan] = field(default_factory=list)


def _flag_kind(sigil: str, glyph: str | None) -> str:
    if sigil == "??":
        return "guessed"
    return "suggested" if glyph else "orphan"


def parse_prepared(text: str) -> ParsedDoc:
    # Split off the definition block: definitions are collected at the
    # document end (spec §4.3); everything from the first definition line on
    # belongs to the block. Definitions are removed from the body so that
    # snippet searches never match inside a definition.
    defs = {int(m.group(1)): m.group(2).strip() for m in DEF_RE.finditer(text)}
    first_def = DEF_RE.search(text)
    body = text[: first_def.start()].rstrip() if first_def else text

    anchors: dict[int, int] = {}
    for m in ANCHOR_RE.finditer(body):
        anchors.setdefault(int(m.group(1)), m.start())

    footnotes = [
        DocFootnote(ident=n, definition=d, anchor_offset=anchors.get(n))
        for n, d in sorted(defs.items())
    ]
    flags = [
        DocFlag(int(m.group(2)), m.start(), _flag_kind(m.group(1), m.group(3)))
        for m in FLAG_RE.finditer(body)
    ]
    cits = [
        DocCitSpan(m.group(1), m.group(2), m.group(3), m.start())
        for m in CIT_RE.finditer(body)
    ]
    page_marks = [(m.group(1), m.start()) for m in PAGE_MARKER_RE.finditer(body)]
    return ParsedDoc(body, page_marks, footnotes, flags, cits)


def page_span(doc: ParsedDoc, label: str) -> tuple[int, int] | None:
    """The body a page marker addresses: from the marker to the next one.

    None where the output never marks that page -- then the candidate has no
    opinion on where the page begins, and nothing can be looked up on it.
    """
    for i, (lbl, off) in enumerate(doc.page_marks):
        if lbl == label:
            end = doc.page_marks[i + 1][1] if i + 1 < len(doc.page_marks) else len(doc.body)
            return (off, end)
    return None


def page_at(doc: ParsedDoc, offset: int) -> str:
    """Printed label of the nearest page marker preceding offset (a marker
    addresses the text that follows it, so its own start is not yet on it)."""
    label = ""
    for lbl, off in doc.page_marks:
        if off < offset:
            label = lbl
        else:
            break
    return label


# plain fallback ----------------------------------------------------------

# "4) Text" / "4. Text" definition lines; N capped and text floor applied,
# otherwise every enumerated list in a foreign output becomes a footnote.
PLAIN_DEF_RE = re.compile(r"^(\d{1,3})[.)]\s+(.{15,})$", re.MULTILINE)
PLAIN_PAGE_LINE_RE = re.compile(r"^\s*\[?(?:p\.|S\.)?\s*(\d{1,4}|[ivxlc]+)\]?\s*$",
                                re.MULTILINE | re.IGNORECASE)


def parse_plain(text: str) -> ParsedDoc:
    defs: dict[int, tuple[str, int]] = {}
    for m in PLAIN_DEF_RE.finditer(text):
        n = int(m.group(1))
        if n <= 400 and n not in defs:
            defs[n] = (m.group(2).strip(), m.start())

    anchors: dict[int, int] = {}
    for m in ANCHOR_RE.finditer(text):
        anchors.setdefault(int(m.group(1)), m.start())
    pandoc_defs = {int(m.group(1)): (m.group(2).strip(), m.start())
                   for m in DEF_RE.finditer(text)}
    defs.update(pandoc_defs)

    footnotes = [
        DocFootnote(ident=n, definition=d, anchor_offset=anchors.get(n))
        for n, (d, _off) in sorted(defs.items())
    ]
    page_marks = [(m.group(1), m.start())
                  for m in PLAIN_PAGE_LINE_RE.finditer(text)]
    page_marks += [(m.group(1), m.start()) for m in PAGE_MARKER_RE.finditer(text)]
    page_marks.sort(key=lambda t: t[1])
    return ParsedDoc(text, page_marks, footnotes, [], [])


ADAPTERS = {"prepared": parse_prepared, "plain": parse_plain}
