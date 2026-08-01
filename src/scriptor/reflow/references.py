"""The reference list: one entry, one paragraph.

A bibliography is set differently from prose and has to be read differently. Sen
et al. set theirs at 6.9pt under a 10.9pt heading, in the *hanging* indent every
reference list uses: the entry opens at the column edge and its continuations are
indented. That is the opposite of a paragraph indent, and the indent rule read it
literally -- every continuation line became a paragraph of its own, so the 29
entries arrived as 71 fragments and no title survived in one piece:

    [1] Akari Asai, Zeqiu Wu, … and Hannaneh Hajishirzi. 2024.

    Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection.

    In Proceedings of ICLR.

A fragment like that is useless twice over. A translator renders "Self-RAG:
Learning to Retrieve" as prose because nothing marks it as a title, and a
retriever indexes three chunks where the citation is one.

So the entries are joined here, before the indent rule and the short-line rule
ever see them: an entry begins at its own ``[N]`` and runs until the next one.
The block ends where the type grows back to body size -- Sen's appendix follows
the references on the next page, and only the type says so.
"""

from __future__ import annotations

import re

# The heading that opens a reference list, in the languages the corpus holds.
# A leading section number is allowed ("8 References"), a trailing colon too.
HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(references|bibliography|works cited|literature|literatur"
    r"(?:verzeichnis)?|bibliographie|bibliografie)\s*:?\s*$",
    re.IGNORECASE,
)

# An entry opens with its own number in brackets: "[12] Nelson F. Liu, …".
ENTRY_RE = re.compile(r"^\[(\d{1,3})\]\s")

# Lines to look ahead for a first entry before believing the heading. A list may
# start on the next page, but not five paragraphs of prose later.
LOOKAHEAD = 4

# The type has to grow by this much before it counts as leaving the block: OCR
# and PDF text layers report the same size with a scatter of a few hundredths.
SIZE_GROWTH = 1.12

# Lines to look past a body-size line for the list continuing. Long enough to
# clear a running head and the entry it interrupts, short enough that a "[1]" in
# some later table cannot reopen a list that ended pages ago.
CONTINUATION_WINDOW = 40

Page = tuple[list[str], list[float | None], list[float | None]]


def _is_entry(line: str) -> bool:
    return bool(ENTRY_RE.match(line.strip()))


def _bare(line: str) -> str:
    """The line without the heading mark ``reflow/headings`` may have put on it."""
    from scriptor.reflow.headings import MARK

    return line.strip().lstrip(MARK)


def _flat(pages: list[Page]) -> list[tuple[int, int, str, float | None]]:
    """(page, index, line, size) for every line of the document, in order."""
    return [
        (p, i, line, sizes[i] if i < len(sizes) else None)
        for p, (lines, sizes, _indents) in enumerate(pages)
        for i, line in enumerate(lines)
    ]


def _block_start(flat: list[tuple[int, int, str, float | None]]) -> int | None:
    """Index into ``flat`` of the first entry line, or None.

    The heading alone does not open a block. "References to the earlier study
    are collected in the appendix" is prose, and a list that never numbers its
    entries cannot be cut into entries anyway.
    """
    for k, (_p, _i, line, _size) in enumerate(flat):
        if not HEADING_RE.match(_bare(line)):
            continue
        for j in range(k + 1, min(k + 1 + LOOKAHEAD, len(flat))):
            if _is_entry(flat[j][2]):
                return j
    return None


def _oversized(size: float | None, block_size: float | None) -> bool:
    return size is not None and block_size is not None and size > block_size * SIZE_GROWTH


def _block_end(flat, start: int, block_size: float | None) -> int:
    """Index after the last line of the block.

    Type growing back to body size ends the list -- unless the list demonstrably
    continues below it. A bibliography running over three pages prints the running
    head on each of them, in body size, in the middle of the block.
    """
    if block_size is None:
        return len(flat)
    for k in range(start, len(flat)):
        if not _oversized(flat[k][3], block_size):
            continue
        window = range(k + 1, min(k + 1 + CONTINUATION_WINDOW, len(flat)))
        if any(_is_entry(flat[j][2]) for j in window):
            continue
        return k
    return len(flat)


def merge_reference_entries(pages: list[Page], *, body_size: float | None) -> list[Page]:
    """Join each reference entry into a single line, page structure preserved.

    ``body_size`` is the document's dominant type size, used only when the block
    itself reports none: a reference list set at body size still has entries.
    """
    flat = _flat(pages)
    start = _block_start(flat)
    if start is None:
        return [(list(l), list(s), list(i)) for l, s, i in pages]

    sizes_in_block = [flat[start][3]] if flat[start][3] is not None else []
    block_size = sizes_in_block[0] if sizes_in_block else body_size
    end = _block_end(flat, start, block_size)

    # Group the block's lines into entries, keyed by the page the entry opens on.
    merged: dict[int, list[tuple[int, list[str]]]] = {}
    claimed: set[tuple[int, int]] = set()
    current: list[str] | None = None
    for k in range(start, end):
        page, index, line, size = flat[k]
        if _oversized(size, block_size):
            # A running head, not a citation. It stays a line of its own so the
            # running-element stripper can still take it out later.
            continue
        claimed.add((page, index))
        if _is_entry(line) or current is None:
            current = [line]
            merged.setdefault(page, []).append((index, current))
        else:
            current.append(line)

    from scriptor.reflow.core import dehyphenate_join

    out: list[Page] = []
    for p, (lines, sizes, indents) in enumerate(pages):
        if p not in merged and not any(page == p for page, _ in claimed):
            out.append((list(lines), list(sizes), list(indents)))
            continue
        # Everything of this page the block did not claim stays as it is.
        page_claimed = {i for page, i in claimed if page == p}
        new_lines: list[str] = []
        new_sizes: list[float | None] = []
        new_indents: list[float | None] = []
        entries = dict(merged.get(p, []))
        for i, line in enumerate(lines):
            if i in entries:
                # The blank line is the paragraph seam parse_page already reads,
                # so one entry becomes one paragraph without a new mechanism.
                new_lines.append("")
                new_sizes.append(None)
                new_indents.append(None)
                new_lines.append(dehyphenate_join([ln.strip() for ln in entries[i]]))
                new_sizes.append(sizes[i] if i < len(sizes) else None)
                # A merged entry is no longer a printed line: it has no left edge
                # the indent rule could read a paragraph break out of.
                new_indents.append(None)
            elif i not in page_claimed:
                new_lines.append(line)
                new_sizes.append(sizes[i] if i < len(sizes) else None)
                new_indents.append(indents[i] if i < len(indents) else None)
        out.append((new_lines, new_sizes, new_indents))
    return out
