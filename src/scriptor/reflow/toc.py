"""TOC detection, preservation, and page-based linking.

Imports ``core`` at module level; ``core`` imports this module only locally
inside its functions (project convention, avoids a cycle).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scriptor.reflow.core import Page, render_frontmatter
from scriptor.reflow.pagelabel import PAGE_MARKER_RE
from scriptor.structure import scheme_of

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
    designator: str = ""   # the number the contents prints, verbatim

    @property
    def text(self) -> str:
        """The entry as the volume prints it: designator and title.

        ``title`` is what a search looks for on a page and has its number
        taken off, because a page may set it differently or not at all. The
        printed form is what the rebuilt contents shows and what the scheme
        table is learnt from -- a level is a level by its number.
        """
        return f"{self.designator} {self.title}".strip()


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


def _split_numbering(title: str, *, roman_present: bool) -> tuple[int, str, str]:
    """(level, designator, title_without_number). Unnumbered -> (1, "", title).

    When the TOC uses roman-numeral outlining (``roman_present``), roman
    numbers form the top level and arabic numbering shifts one level deeper.
    Without roman numbers, arabic numbering stays 1-based as before.

    The designator is handed back rather than thrown away. It is what the
    volume printed, so the rebuilt contents shows it -- Bauer's link list read
    "Aneignung als Rechtsbegriff" where the page reads "I. Aneignung als
    Rechtsbegriff", and 120 of its 178 entries had lost their number that way.
    """
    bullet = _BULLET_PREFIX.match(title)
    if bullet:
        # One level below whatever the volume calls its top. The bullet is not
        # part of the title -- the page is set without it -- but it is part of
        # what the contents prints, and it is the only thing stating the rank.
        inner_level, inner_designator, inner = _split_numbering(
            bullet.group("rest"), roman_present=roman_present)
        mark = title.strip()[0]
        return (max(inner_level, 1) + 1,
                f"{mark} {inner_designator}".strip(), inner)
    if roman_present:
        rm = _ROMAN_PREFIX.match(title)
        if rm:
            return 1, f"{rm.group('rom')}.", rm.group("rest").strip()
    m = _NUM_PREFIX.match(title)
    if m:
        depth = m.group(1).count(".") + 1
        designator = title[: m.start("rest")].strip()
        return depth + (1 if roman_present else 0), designator, m.group("rest").strip()
    return 1, "", title


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


# How many wrapped halves may stand over one entry. A three-line entry is a
# real shape -- Bauer's "b) Verletzung des unbenannten Rechts der öffentlichen /
# Wiedergabe gem. § 15 Abs. 2 ... / ... 231" -- and joining only the line
# directly above it left its head standing as an entry of its own. Two is where
# it stops: a run longer than that is not one title but a block of lines the
# parser has no business folding into the next number it sees.
_MAX_WRAP_LINES = 2


@dataclass
class _Line:
    """One line of the contents, before anything is decided about it."""

    text: str                 # the line as it stands
    title: str                # its title part, where it ends in a page number
    page: int | None          # that number
    alone: bool               # a thing in its own right, never half an entry
    opens_page: bool = False


def _demote_dips(lines: list[_Line]) -> int:
    """Take the number off a line whose page falls below both its neighbours.

    A contents rises. "b) ... nach § 24 Abs. 1" reads as an entry on page 1
    between entries on 230 and 231, and the shape of that mistake is a single
    step out of the running sequence and straight back into it. A series that
    genuinely restarts -- an appendix numbered afresh -- steps down and stays
    down, so the entry after it does not reach the one before. Bauer loses
    part of 36 entries this way, and the parser had no plausibility check of
    the sequence at all.
    """
    numbered = [line for line in lines if line.page is not None]
    demoted = 0
    for k in range(1, len(numbered) - 1):
        here, after = numbered[k], numbered[k + 1]
        # The running sequence is what is left of it: a line demoted a moment
        # ago states no page any more and cannot be the one this rises from.
        before = next((x for x in reversed(numbered[:k]) if x.page is not None),
                      None)
        if before is not None and here.page < before.page <= after.page:
            here.page, here.title = None, ""
            here.alone = _stands_alone(here.text)
            demoted += 1
    return demoted


def _read_lines(pages: list[Page]) -> tuple[list[_Line], int]:
    out: list[_Line] = []
    non_empty = 0
    for p in pages:
        opens = True
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
            # Leaders run from the title to its number, and not only as dots:
            # Masones sets a pipe ("Nota preliminar | 10"), others a middle dot
            # or an ellipsis. None of them is part of the title.
            #
            # A bullet is not among them. It stands *before* the title, where it
            # states a rank (_BULLET_PREFIX), and stripping it here would throw
            # that away before anyone asks -- which is how six of Carlomagno's
            # sections came out as chapters.
            title = m.group("title").strip(" .·|–—…\t") if m else ""
            out.append(_Line(text=s, title=title,
                             page=int(m.group("page")) if m and title else None,
                             alone=_stands_alone(s), opens_page=opens))
            opens = False
    return out, non_empty


def parse_toc(pages: list[Page]) -> TocParse:
    lines, non_empty = _read_lines(pages)
    _demote_dips(lines)

    raw: list[tuple[str, int]] = []   # (title_with_number, page)
    # The lines above, where they carried no page number and could be the
    # first halves of an entry that wrapped. Between a quarter and a half of
    # the lines in this corpus' contents lists have no number, and wrapped
    # titles are the largest group among them: Masones loses nine of its
    # fourteen chapters that way, leaving "Escocesa | 36" and "cia | 107".
    pending: list[str] = []
    for line in lines:
        if line.opens_page:
            pending.clear()         # a wrap does not cross a page break
        if line.page is None:
            if line.alone:
                pending.clear()
            else:
                pending.append(line.text)
                del pending[:-_MAX_WRAP_LINES]
            continue
        # A line that opens with a designator of its own opens an entry, and
        # an entry is not the second half of the one above it. Without that
        # test a contents whose page numbers the parser cannot read -- roman
        # numerals, a tab instead of leaders -- folds whole runs of its
        # entries into the next number it does read (Artificial Humanities
        # merged "2.6.1", "2.6.2" and "Chapter 3" into one).
        if pending and not scheme_of(line.title, roman_volume=True)[0]:
            title = " ".join(pending + [line.title]).strip()
        else:
            title = line.title
        pending.clear()
        if title:
            raw.append((title, line.page))

    # Only assume a roman-numeral scheme if >=2 entries start that way
    # (a lone "M." is more likely an initial than a chapter number).
    roman_present = sum(1 for t, _ in raw if _ROMAN_PREFIX.match(t)) >= 2
    entries: list[TocEntry] = []
    for t, pg in raw:
        level, designator, title = _split_numbering(t, roman_present=roman_present)
        if title:
            entries.append(TocEntry(title=title, page=pg, level=level,
                                    designator=designator))

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


def printed_heading(page: Page) -> str | None:
    """The heading this page prints above its TOC entries, or None.

    Conservative: only the first non-empty line, only when it is not itself an
    entry, is short, and carries letters. ``parse_toc`` still counts the line
    among the non-entry lines, so the confidence heuristic is unaffected.
    """
    pages = [page]
    if pages[0].heading and is_contents_heading(pages[0].heading):
        # The outline named it and the page confirmed it, so chapter_headings
        # lifted the line out of the body before anyone got here. It is still
        # the heading this volume prints over its list, and dropping it costs
        # the contents its own name -- Bauer's "Inhaltsverzeichnis" and
        # "Abbildungsverzeichnis" both went that way.
        return pages[0].heading.strip()
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
                lines.append(f"{indent}- [{e.text}](#p-{label}) — p. {label}")
                targets.add(label)
            elif e.page >= 0:
                lines.append(f"{indent}- {e.text} — p. {label}")
            else:
                lines.append(f"{indent}- {e.text}")
        heading = (printed_heading(pages[0]) if pages else None) or FALLBACK_HEADING
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
