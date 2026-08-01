"""Run-in headings: the ones the typesetter put inside the paragraph.

Scholarly articles set the lowest level of their outline *into* the first line
of the text it introduces. Sen et al. p.3 prints one printed line that reads

    3.2.1 Lexical Search (Grep). The grep retrieval tool loads conversation

where "3.2.1 Lexical Search (Grep)." is italic and the rest roman. By text alone
the two are indistinguishable -- the title ends at a period, and so does many a
sentence. The typography says it outright, so that is what is read here: the
emphasised head of the line, cut off where the roman type begins.

Emphasis alone decides nothing. An italic work title opening a line ("*Römische
Geschichte*, so Mommsen, …") is a title, not a heading; a section number has to
stand in front of it. That keeps the rule from firing on the one thing italics
are actually common for in this corpus.
"""

from __future__ import annotations

import re

# "3", "3.2", "3.2.1", with or without a closing period, followed by a title that
# begins with a letter. Zuckerman's OCR layer hands over the folio as "2 0 8" and
# reports it italic; without the letter that reads as section 2, title "0 8".
SECTION_NUMBER_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+[^\W\d_]")

# A run-in heading is a title, not a sentence: this many characters and it is
# prose that happens to start in italics.
MAX_HEADING_CHARS = 90

# Carries "the typesetter set this whole line apart" the one step from here to
# ``heading_level``, which sees text and nothing else. It buys the case text
# cannot decide: "3 Methodology" is a chapter, "44 The Surrender of Narbonne" is
# Zuckerman's folio with its running head, and only the type tells them apart.
# From the Private Use Area, so no document can contain it; ``reconstruct_body``
# strips it off the line it reads.
MARK = ""


def split_emphasised_headings(
    lines: list[str],
    emphases: list[int],
    sizes: list[float | None],
    indents: list[float | None],
) -> tuple[list[str], list[float | None], list[float | None]]:
    """Cut each run-in heading off the paragraph it opens.

    Returns lines, sizes and indents, still parallel. The remainder of a cut line
    carries no indent: its left edge belongs to the heading, and the indent rule
    must not read a paragraph break out of it.
    """
    out_lines: list[str] = []
    out_sizes: list[float | None] = []
    out_indents: list[float | None] = []

    after_heading = False
    for i, line in enumerate(lines):
        run = emphases[i] if i < len(emphases) else 0
        size = sizes[i] if i < len(sizes) else None
        indent = indents[i] if i < len(indents) else None
        head, rest = line[:run].strip(), line[run:].strip()

        # A heading too long for one line: the emphasis runs on, the number does
        # not. Only a heading's own continuation inherits the mark — emphasis
        # after ordinary prose is a work title, not a second line.
        if after_heading and not rest and head and not SECTION_NUMBER_RE.match(head):
            out_lines.append(MARK + head)
            out_sizes.append(size)
            out_indents.append(indent)
            continue
        after_heading = False

        if (
            run
            and head
            and len(head) <= MAX_HEADING_CHARS
            and SECTION_NUMBER_RE.match(head)
        ):
            after_heading = not rest
            if rest:
                out_lines.extend([MARK + head, rest])
                out_sizes.extend([size, size])
                out_indents.extend([indent, None])
            else:
                # The whole line is the heading; it only needs the mark.
                out_lines.append(MARK + head)
                out_sizes.append(size)
                out_indents.append(indent)
            continue

        out_lines.append(line)
        out_sizes.append(size)
        out_indents.append(indent)

    return out_lines, out_sizes, out_indents
