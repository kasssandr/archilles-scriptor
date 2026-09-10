"""Candidate-output adapters.

parse_prepared() reads spec-conform prepared Markdown; it lives in
``scriptor.document``, the format's reference consumer, and is used here
unchanged. parse_plain() (Task 4) is the fallback for foreign converter output.
Both produce the same ParsedDoc shape; every metric consumes only that.
"""
from __future__ import annotations

import re

from scriptor.document import (  # noqa: F401 -- the metrics import these from here
    ANCHOR_RE,
    DEF_RE,
    DocCitSpan,
    DocFootnote,
    ParsedDoc,
    page_at,
    page_span,
    parse_prepared,
    region_at,
)
from scriptor.reflow.pagelabel import PAGE_MARKER_RE


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
