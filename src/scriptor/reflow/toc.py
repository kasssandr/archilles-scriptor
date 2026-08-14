"""TOC detection, preservation, and page-based linking.

Imports ``core`` at module level; ``core`` imports this module only locally
inside its functions (project convention, avoids a cycle).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scriptor.reflow.core import Page, render_frontmatter
from scriptor.reflow.pagelabel import PAGE_MARKER_RE

TOC_LINK_THRESHOLD = 0.7

# Line ends with a plausible page number (1-4 digits).
_LINE_ENDS_NUM = re.compile(r"\d{1,4}\s*$")

# Clean entry line: title + (leader/whitespace) + trailing number.
_ENTRY_RE = re.compile(r"^(?P<title>.*?\S)[\s.]*\s(?P<page>\d{1,4})$")

# Leading outline number: 1 / 1.1 / 1.1.2 …
_NUM_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(?P<rest>.*)$")

# Leading uppercase roman-numeral outline number: I. / II. / IV. / XII. …
# The period right after the number disambiguates against words ("VICTORIA.").
_ROMAN_PREFIX = re.compile(
    r"^(?=[MDCLXVI])"
    r"(?P<rom>M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))"
    r"\.\s+(?P<rest>\S.*)$"
)

# Page marker: [p. LABEL] — one definition, shared with core and confidence.
_PAGE_MARKER_RE = PAGE_MARKER_RE


@dataclass
class TocEntry:
    title: str
    page: int          # printed page number per the TOC; -1 if none
    level: int         # 1-based; 1 = top level


@dataclass
class TocParse:
    entries: list[TocEntry]
    confidence: float


@dataclass
class TocRender:
    blocks: list[str]
    anchor_targets: set[str] = field(default_factory=set)


# A heading printed over a table of contents, in the two shapes a printer gives
# it. The words themselves are already known (regions.region_of_heading covers
# Sumário, TABLE DES MATIÈRES, Inhoudsopgave, Содержание and the rest); what
# needs undoing is the typography.
#
# This is how a contents list is told from a name register, and it is the only
# test that works: position does not (four of the eighteen corpus volumes carry
# their contents at the back — L'Empire and Les apologistes set a table des
# matières at 97–98 % of the book, as romance typography has always done), and
# confidence does not either (parse_toc scores the real contents of Making
# Martyrs at 0.45 and Themistios' register at 0.53). What holds is what the
# volume writes over it. No contents page in this corpus carries the book's
# title; every one carries "Índice" or its equivalent.
_SPACED_OUT = re.compile(r"^(?:\S\s+){3,}\S\s*$")


def _unspace(line: str) -> str:
    """Undo letterspacing: 'S u m á r i o' -> 'Sumário'.

    Only where the line is *nothing but* single characters and spaces. A line
    that merely starts with one ("I. Die Antike") keeps its spaces, or every
    numbered heading in the corpus would collapse into a word.
    """
    return re.sub(r"\s+", "", line) if _SPACED_OUT.match(line.strip()) else line


def is_contents_heading(line: str) -> bool:
    """True if this line is the heading a volume prints over its contents."""
    from scriptor.reflow.regions import region_of_heading
    from scriptor.reflow.running_elements import _normalize_header_line

    s = line.strip()
    if not s:
        return False
    for candidate in (s, _normalize_header_line(s), _unspace(s),
                      _unspace(_normalize_header_line(s))):
        if candidate and region_of_heading(candidate) == "contents":
            return True
    return False


def is_toc_page(
    page: Page,
    *,
    min_entry_lines: int = 4,
    page_end_fraction: float = 0.6,
) -> bool:
    """True if a sufficient fraction of non-empty lines ends in a page number
    (structural, heading-less TOC heuristic)."""
    lines = [ln.strip() for ln in page.body_lines if ln.strip()]
    if len(lines) < min_entry_lines:
        return False
    ending = sum(1 for ln in lines if _LINE_ENDS_NUM.search(ln))
    return ending >= min_entry_lines and ending / len(lines) >= page_end_fraction


# A bullet in a contents list is a rank, not decoration. Carlomagno separates
# its levels by nothing else: seven chapters set in capitals with a roman
# number, fifty-one sections each opened by "•". Dropping the bullet before
# asking what an entry is -- which the chapter search did -- throws away the
# only thing that says so, and six sections came out as chapters.
_BULLET_PREFIX = re.compile(r"^\s*[•▪◦‣*]\s*(?P<rest>\S.*)$")


def _split_numbering(title: str, *, roman_present: bool) -> tuple[int, str]:
    """(level, title_without_number). Unnumbered -> (1, title).

    When the TOC uses roman-numeral outlining (``roman_present``), roman
    numbers form the top level and arabic numbering shifts one level deeper.
    Without roman numbers, arabic numbering stays 1-based as before.
    """
    bullet = _BULLET_PREFIX.match(title)
    if bullet:
        # One level below whatever the volume calls its top -- and the bullet
        # itself is not part of the title, which is set without it on the page.
        inner_level, inner = _split_numbering(bullet.group("rest"),
                                              roman_present=roman_present)
        return max(inner_level, 1) + 1, inner
    if roman_present:
        rm = _ROMAN_PREFIX.match(title)
        if rm:
            return 1, rm.group("rest").strip()
    m = _NUM_PREFIX.match(title)
    if m:
        depth = m.group(1).count(".") + 1
        return depth + (1 if roman_present else 0), m.group("rest").strip()
    return 1, title


# A line without a page number that is a thing in its own right, not the first
# half of an entry that wrapped. Two kinds occur in this corpus:
#
#   the heading over the list        "ÍNDICE", "S u m á r i o"
#   a chapter mark between entries   "CAPÍTULO VI", "PRIMERA PARTE"
#
# The second matters as much as the first: Masones prints 'CAPÍTULO VI' between
# the last section of chapter V (page 90) and the first of chapter VI (page 93),
# and joining it downward would merge a boundary into an entry.
_CHAPTER_MARK = re.compile(
    r"(?i)^\s*(?:cap[íi]tulo|chapter|kapitel|hoofdstuk|capitolo|chapitre|"
    r"parte|part|teil|deel|libro|book|buch|tomo|volume|band)"
    r"[\s.:—–-]*[IVXLCDM\d]*\s*$"
)


# How long the first half of a wrapped title may be. A title that does not fit
# on a line is still a title; what is longer than this is something else that
# happens to carry no page number.
_MAX_WRAP_HALF = 90


def _stands_alone(line: str) -> bool:
    """True if this numberless line is its own thing, not half an entry.

    Three kinds occur: the heading over the list, a chapter mark between
    entries, and a line the reflow has already turned into something else. The
    last one is bauer-aneignung, part of whose contents is set as a table and
    arrives as Markdown -- appending "| B. | Gang der Darstellung | | 23 || ---"
    to the title above it produces exactly the monstrosity it looks like.
    """
    if "|" in line or line.lstrip().startswith(("#", ">", "-")):
        return True
    if len(line) > _MAX_WRAP_HALF:
        return True
    return bool(_CHAPTER_MARK.match(line)) or is_contents_heading(line)


def parse_toc(pages: list[Page]) -> TocParse:
    raw: list[tuple[str, int]] = []   # (title_with_number, page)
    non_empty = 0
    # The line above, when it carried no page number and could be the first
    # half of an entry that wrapped. Between a quarter and a half of the lines
    # in this corpus' contents lists have no number, and wrapped titles are the
    # largest group among them: Masones loses nine of its fourteen chapters
    # that way, leaving "Escocesa | 36" and "cia | 107" behind.
    pending: str | None = None
    for p in pages:
        for ln in p.body_lines:
            s = ln.strip()
            if not s:
                # A blank line does not end a wrapped title here. The indent
                # that marks the continuation ("Escocesa" set at x=104 under
                # its title at x=89) is exactly what mark_indent_breaks turns
                # into a blank line further up the pipeline -- the very signal
                # this needs arrives as its own destruction.
                continue
            non_empty += 1
            m = _ENTRY_RE.match(s)
            if not m or not m.group("title").strip():
                # No number: the first half of a wrapped entry, or a line that
                # belongs to nobody. Only the line *directly* above an entry is
                # ever joined -- a run of them is not one title, and joining
                # would swallow whatever stands over it.
                pending = None if _stands_alone(s) else s
                continue
            # Leaders run from the title to its number, and not only as dots:
            # Masones sets a pipe ("Nota preliminar | 10"), others a middle dot
            # or an ellipsis. None of them is part of the title.
            #
            # A bullet is not among them. It stands *before* the title, where it
            # states a rank (_BULLET_PREFIX), and stripping it here would throw
            # that away before anyone asks -- which is how six of Carlomagno's
            # sections came out as chapters.
            title = m.group("title").strip(" .·|–—…\t")
            if pending:
                title = f"{pending} {title}".strip()
                pending = None
            if title:
                raw.append((title, int(m.group("page"))))
        pending = None      # a wrap does not cross a page break

    # Only assume a roman-numeral scheme if >=2 entries start that way
    # (a lone "M." is more likely an initial than a chapter number).
    roman_present = sum(1 for t, _ in raw if _ROMAN_PREFIX.match(t)) >= 2
    entries: list[TocEntry] = []
    for t, pg in raw:
        level, title = _split_numbering(t, roman_present=roman_present)
        if title:
            entries.append(TocEntry(title=title, page=pg, level=level))

    confidence = len(entries) / non_empty if non_empty else 0.0
    seq = [e.page for e in entries if e.page >= 0]
    if len(seq) >= 2:
        non_decr = sum(1 for a, b in zip(seq, seq[1:]) if b >= a)
        mono = non_decr / (len(seq) - 1)
        confidence *= 0.5 + 0.5 * mono
    return TocParse(entries=entries, confidence=confidence)


_VERBATIM_MARKER = (
    "[Table of contents preserved verbatim; page linking skipped because the "
    "column layout could not be read reliably]"
)

# Text scriptor *preserves* speaks the book's language; text scriptor *adds*
# speaks the tool's, which is English — the same voice as the audit sidecar.
# A table of contents prints its own heading ("INHALT", "CONTENTS"), so that one
# is carried over verbatim instead of being invented, exactly as a printed page
# label is. Only where the book prints none does the tool supply this fallback:
# dropping the heading entirely would cost the TOC its section identity, which
# downstream chunking relies on.
FALLBACK_HEADING = "Contents"
_MAX_HEADING_LEN = 50


def _printed_heading(pages: list[Page]) -> str | None:
    """The heading the book prints above its TOC entries, or None.

    Conservative: only the first non-empty line of the first page, only when it
    is not itself an entry, is short, and carries letters. ``parse_toc`` still
    counts the line among the non-entry lines, so the confidence heuristic is
    unaffected by this.
    """
    if not pages:
        return None
    for ln in pages[0].body_lines:
        s = ln.strip()
        if not s:
            continue
        if _ENTRY_RE.match(s):
            return None  # entries start immediately: nothing was printed above
        letters = sum(1 for c in s if c.isalpha())
        return s if letters >= 2 and len(s) <= _MAX_HEADING_LEN else None
    return None


def render_toc(pages: list[Page], available_pages: set[str]) -> TocRender:
    parse = parse_toc(pages)
    if parse.confidence >= TOC_LINK_THRESHOLD and parse.entries:
        lines: list[str] = []
        targets: set[str] = set()
        for e in parse.entries:
            indent = "  " * (e.level - 1)
            # Anchors key on the page *label*, never on its ordinal: roman "xiv"
            # and arabic "14" share an ordinal but are different pages, and a
            # shared anchor id would send the link into the front matter.
            label = str(e.page)
            if e.page >= 0 and label in available_pages:
                lines.append(f"{indent}- [{e.title}](#p-{label}) — p. {label}")
                targets.add(label)
            elif e.page >= 0:
                lines.append(f"{indent}- {e.title} — p. {label}")
            else:
                lines.append(f"{indent}- {e.title}")
        heading = _printed_heading(pages) or FALLBACK_HEADING
        return TocRender(blocks=[f"## {heading}", "\n".join(lines)],
                         anchor_targets=targets)

    blocks = [_VERBATIM_MARKER]
    blocks.extend(render_frontmatter(pages))
    return TocRender(blocks=blocks, anchor_targets=set())


def inject_page_anchors(doc: str, targets: set[str]) -> str:
    """Appends ``{#p-LABEL}`` to the first ``[p. LABEL]`` of every target label."""
    remaining = set(targets)

    def repl(m: re.Match[str]) -> str:
        label = m.group(1)
        if label in remaining:
            remaining.discard(label)
            return f"[p. {label}]{{#p-{label}}}"
        return m.group(0)

    return _PAGE_MARKER_RE.sub(repl, doc)
