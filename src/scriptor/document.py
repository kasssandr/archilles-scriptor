"""Reading a prepared document -- the format's reference consumer.

``parse_prepared`` reads spec-conform prepared Markdown (PREPARED_FORMAT_SPEC):
the metadata block is dropped, region, page and footnote markers, flags and
citation spans are read, all with offsets into the remaining text. The reach
rule a consumer needs on top of that -- which page and which region a position
is in -- is ``page_at`` and ``region_at``.

``load_bundle`` adds what travels beside the master (spec §3, §6.3, §6.5): the
fields of the metadata block, the pagination sidecar, which carries the physical
page and the witness behind each label, and the structure sidecar, which carries
the division -- the true depth of every heading and the level the chapters open
on, neither of which the master's six hashes can say.

``Bundle.locate`` resolves an address (spec §4.7): a printed page, the
occurrence where a label repeats, and a wording of at least
``MIN_WORDING_WORDS`` words. The wording is a checksum, not a pointer -- where
the page no longer carries it the answer is None, and the same words elsewhere
in the volume are never silently taken instead. ``nearest`` may offer another
page as a *proposal*. This is measured ground: P-M2 resolved 1437 addresses
through three productions and three kinds of edit without one silent error.

The reader lived in ``eval/``, the benchmark's workshop, where no consumer may
import from. Here it is the one place that knows the grammar; the benchmark and
archilles both read through it rather than keeping a copy.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scriptor.reflow.outline import fold
from scriptor.reflow.pagelabel import PAGE_MARKER_RE
from scriptor.reflow.pagination.report import SIDECAR_VERSION
from scriptor.structure import (
    SchemeTable,
    Structure,
    read_structure_sidecar,
    structure_of,
)

# Spec §5 flag grammar. Group 1: sigil (? or ??), 2: printed number,
# 3: candidate glyph (absent on orphan flags).
FLAG_RE = re.compile(r"\[(\?\??)FN:(\d+)(?:\|([^\]:]+)(?::0?\.\d)?)?\]")
# Spec §4.3 / Pandoc: anchors and definitions. A definition runs on over the
# lines that follow it, up to a blank line or the next definition -- Pandoc's
# lazy continuation. Scriptor writes such lines where a note's text kept a
# line break; reading only the first line lost them.
ANCHOR_RE = re.compile(r"\[\^(\d+)\]")
DEF_RE = re.compile(r"^\[\^(\d+)\]:[ \t]*(.*(?:\n(?![ \t]*$)(?!\[\^\d+\]:).*)*)",
                    re.MULTILINE)
# Spec §8 citation spans: [text]{.cit type=r3 ref=key}
CIT_RE = re.compile(
    r"\[([^\]]+)\]\{\.cit\s+type=(r[34])(?:\s+ref=([\w:-]+))?\}"
)
# Spec §4.4 region markers, each on a line of its own.
REGION_LINE_RE = re.compile(r"^\[region:\s*([a-z-]+)\]\s*\n?", re.MULTILINE)


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
    region_marks: list[tuple[str, int]] = field(default_factory=list)


def _split_region_marks(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Lift the §4.4 markers out of the text, keeping where each took effect.

    They are declaration, not prose -- and unlike a page marker they carry a
    *word*, so leaving them in would let a snippet search match `bibliography`
    in a document that merely names the region. Offsets returned are already
    those of the cleaned text.
    """
    marks: list[tuple[str, int]] = []
    out: list[str] = []
    kept = 0
    last = 0
    for m in REGION_LINE_RE.finditer(text):
        out.append(text[last:m.start()])
        kept += m.start() - last
        marks.append((m.group(1), kept))
        last = m.end()
    out.append(text[last:])
    return "".join(out), marks


def _flag_kind(sigil: str, glyph: str | None) -> str:
    if sigil == "??":
        return "guessed"
    return "suggested" if glyph else "orphan"


def parse_prepared(text: str) -> ParsedDoc:
    # The §4.1 metadata block is declaration, not text: dropping it here keeps
    # a snippet search from ever matching a field name, and keeps every offset
    # below counted from the document's first word.
    from scriptor.reflow.regions import strip_metadata_block

    text = strip_metadata_block(text)
    text, region_marks = _split_region_marks(text)
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
    return ParsedDoc(body, page_marks, footnotes, flags, cits,
                     [(n, o) for n, o in region_marks if o <= len(body)])


def _preceding(marks: list[tuple[str, int]], offset: int, *,
               inclusive: bool = False) -> str:
    value = ""
    for name, off in marks:
        if off < offset or (inclusive and off == offset):
            value = name
        else:
            break
    return value


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
    return _preceding(doc.page_marks, offset)


def region_at(doc: ParsedDoc, offset: int) -> str:
    """Region in force at offset; "" before the first marker. Same reach rule
    as the page label -- a region runs until the next one opens. Unlike a page
    marker it is lifted out of the body, so its own offset already belongs to
    it: the text that moved into that position is inside the region."""
    return _preceding(doc.region_marks, offset, inclusive=True)


# the text match ----------------------------------------------------------

# ``normalize`` maps text to a canonical form (casefold, single spaces, soft
# hyphens dropped, line-break hyphenation joined); ``find_snippet`` searches a
# normalized needle but answers with offsets into the ORIGINAL haystack, via a
# position map built while normalizing. A metric, and an address, must report
# positions a human can find in the real file. Both lived in ``eval/``, the
# benchmark's workshop, which no consumer may import from; they are the match
# an address is resolved with, so they live here and the benchmark reads them
# from here (the move ``parse_prepared`` made before them).

_SOFT_HYPHEN = "­"


def _normalized_with_map(text: str) -> tuple[str, list[int]]:
    """Returns (normalized text, map: normalized index -> original index)."""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    posmap: list[int] = []
    i, n = 0, len(text)
    pending_space = False
    while i < n:
        ch = text[i]
        if ch == _SOFT_HYPHEN:
            i += 1
            continue
        # line-break hyphenation: "-\n" between letters joins the word
        if (ch == "-" and i + 1 < n and text[i + 1] == "\n"
                and out and out[-1].isalpha()
                and i + 2 < n and text[i + 2].isalpha()):
            i += 2
            continue
        if ch.isspace():
            pending_space = True
            i += 1
            continue
        if pending_space and out:
            out.append(" ")
            posmap.append(i)          # space attributed to the following char
        pending_space = False
        for c in ch.casefold():       # casefold may expand (ß -> ss)
            out.append(c)
            posmap.append(i)
        i += 1
    return "".join(out), posmap


def normalize(text: str) -> str:
    return _normalized_with_map(text)[0]


def find_snippet(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate normalized needle in haystack; return original-offset span."""
    norm_hay, posmap = _normalized_with_map(haystack)
    norm_needle = normalize(needle)
    if not norm_needle:
        return None
    idx = norm_hay.find(norm_needle)
    if idx < 0:
        return None
    start = posmap[idx]
    last = idx + len(norm_needle) - 1
    end = posmap[last] + 1
    return (start, end)


# What a new production renumbers or moves and a reader does not read: note
# anchors, page markers with their Pandoc anchors, the backslash of an escape,
# and the hashes of a heading -- a production that levels a heading differently
# changes them and no word. Measured: the first P-M2 run lost five of eighty
# matches to '#' against '####' alone.
_MARK_RE = re.compile(r"\[\^\d+\]|\[p\. [^\]\n]+\](?:\{#[^}\n]*\})?|\\(?=[*_])"
                      r"|(?m:^#{1,6}[ \t]+)")


def blind(text: str) -> tuple[str, list[int]]:
    """``text`` without markers, and for every kept character where it stood."""
    out: list[str] = []
    pos: list[int] = []
    last = 0
    for m in _MARK_RE.finditer(text):
        out.append(text[last:m.start()])
        pos.extend(range(last, m.start()))
        last = m.end()
    out.append(text[last:])
    pos.extend(range(last, len(text)))
    return "".join(out), pos


# the master's headings ---------------------------------------------------

# Spec §4.2: a heading is an ATX line of one to six hashes. Seven are a
# paragraph that begins with hashes, in CommonMark as in Obsidian, which is
# why a deeper level is written with six and its true depth travels in the
# structure sidecar (Briefing §8.3).
HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(\S[^\n]*?)[ \t]*$", re.MULTILINE)
# A heading that opens a page stands *before* that page's marker, so a run of
# headings in front of a marker belongs to the page the marker names.
_OPENS_PAGE_RE = re.compile(r"\s*(?:#{1,6}[ \t][^\n]*\n\s*)*\[p\. ([^\]]+)\]")


@dataclass(frozen=True)
class MasterHeading:
    """One ``#`` line of a master, with where it stands."""
    marks: int          # how many hashes -- the printed level, at most six
    text: str           # the line's text, verbatim (emphasis and all)
    page: str           # the printed label it stands on; "" where none does
    region: str         # the region in force there; "" before the first marker
    start: int          # offset into ``doc.body``
    end: int


def master_headings(doc: ParsedDoc) -> list[MasterHeading]:
    """The ``#`` lines of ``doc``, in document order.

    The structure sidecar (spec §6.5) lists exactly these, in this order: the
    master says how many headings a volume has, the sidecar how deep each one
    really is.
    """
    out: list[MasterHeading] = []
    for m in HEADING_LINE_RE.finditer(doc.body):
        opens = _OPENS_PAGE_RE.match(doc.body, m.end())
        page = opens.group(1) if opens else page_at(doc, m.start())
        out.append(MasterHeading(marks=len(m.group(1)), text=m.group(2), page=page,
                                 region=region_at(doc, m.start()),
                                 start=m.start(), end=m.end()))
    return out


# How far ahead of the heading it expects a producer's depth may stand: a
# stray '#' in passed-through front matter is a '#' line the render never
# wrote, and the two lists have to find each other again after one.
_DEPTH_REACH = 4


def structure_of_master(text: str, depths: Sequence[tuple[int, str]],
                        table: SchemeTable, **kw) -> Structure:
    """The structure of the master ``text``, listing its ``#`` lines in order.

    ``depths`` is what the producer knows and the master cannot say: the true
    depth of each heading it wrote, past the six levels Markdown has (§8.3).
    The two lists are joined on the wording, one heading at a time, so that a
    line neither of them expected -- a '#' that came through in front matter --
    costs only itself: it keeps the depth its hashes print.
    """
    doc = parse_prepared(text)
    heads = master_headings(doc)
    lines: list[tuple[int, str]] = []
    k = 0
    for h in heads:
        ahead = range(k, min(k + _DEPTH_REACH, len(depths)))
        j = next((i for i in ahead if depths[i][1] == h.text), None)
        lines.append((h.marks if j is None else depths[j][0], h.text))
        if j is not None:
            k = j + 1
    return structure_of(lines, table, pages=[h.page or None for h in heads], **kw)


# the bundle --------------------------------------------------------------

@dataclass(frozen=True)
class SidecarPage:
    """One position of the pagination sidecar (spec §6.3)."""
    pos: int                       # physical page, 1-based
    label: str                     # as printed, verbatim
    source: str                    # the strongest witness; unknown values kept as they are
    confidence: float | None = None


# An address carries at least this many words of the passage it names. Measured
# (P-M2, Briefing §8): at eight words 1437 addresses of two volumes resolved
# through three productions and three kinds of edit with no silent error; nine
# of them found a second, word-identical place on the same page, and every one
# of those is reported as ``ambiguous``. Sixteen words would end the ambiguity
# and would not fit in every fifth paragraph.
MIN_WORDING_WORDS = 8

# How far a proposal may reach (spec §4.7). Three pages in both directions: a
# passage that a new edition moved further than that is a different passage.
NEAREST_REACH = 3


@dataclass(frozen=True)
class Locus:
    """Where a wording stands: its address, and the offsets it resolved to.

    ``start`` and ``end`` are offsets into ``Bundle.doc.body`` -- a cache, like
    ``pos``, the physical page from the pagination sidecar. The address is
    ``page``, ``occurrence`` and the wording that was asked for.
    """
    page: str
    occurrence: int
    pos: int | None
    start: int
    end: int
    proposed: bool = False    # not the page that was asked for, only the nearest
    ambiguous: bool = False   # the page carries the wording more than once
    label_source: str | None = None   # the witness behind the label (spec §6.3)


def _wording_of(wording: str) -> str:
    """The normalized needle, or ValueError where the wording is too short.

    Counted blind to markers: an anchor between two words is not a word, and a
    wording is written from the master, markers and all.
    """
    clean = blind(wording)[0]
    if len(clean.split()) < MIN_WORDING_WORDS:
        raise ValueError(f"a wording carries at least {MIN_WORDING_WORDS} words, "
                         f"this one {len(clean.split())}: {wording!r}")
    return normalize(clean)


@dataclass
class Bundle:
    """A master and what travels beside it.

    ``pages`` is empty where the sidecar is missing or found no printed number;
    every lookup then answers None, which is what "unknown" means here.
    """
    master: Path
    text: str
    metadata: dict[str, str]
    pages: list[SidecarPage] = field(default_factory=list)
    structure: Structure | None = None   # the division, where a sidecar carries it

    def __post_init__(self) -> None:
        self.pages = sorted(self.pages, key=lambda p: p.pos)
        self._by_label: dict[str, list[SidecarPage]] = {}
        for p in self.pages:
            self._by_label.setdefault(p.label, []).append(p)
        self._doc: ParsedDoc | None = None
        self._headings: list[MasterHeading] | None = None
        self._resolved: list[SidecarPage | None] | None = None
        self._searchable: dict[int, tuple[list[int], str, list[int]]] = {}

    @property
    def format_version(self) -> str:
        return self.metadata["format_version"]

    @property
    def chunking_strategy(self) -> str:
        """Spec §4.1: every field is optional, and the absent strategy is basic."""
        return self.metadata.get("chunking_strategy", "basic")

    @property
    def pagination(self) -> str | None:
        return self.metadata.get("pagination")

    @property
    def chapter_level(self) -> int | None:
        """The depth on which this volume opens its chapters, or None where no
        sidecar says. Declared, never guessed from the hashes: a volume whose
        parts are ``#`` sets its chapters on 2, one without parts on 1."""
        return self.structure.chapter_level if self.structure else None

    def _only(self, label: str) -> SidecarPage | None:
        """The one sidecar page carrying ``label`` -- None where no page does,
        and None where several do: a volume in parts restarts its numbering,
        and a label alone then names no single page."""
        found = self._by_label.get(label, [])
        return found[0] if len(found) == 1 else None

    def physical_page_of(self, label: str) -> int | None:
        entry = self._only(label)
        return entry.pos if entry else None

    def source_of(self, label: str) -> str | None:
        entry = self._only(label)
        return entry.source if entry else None

    def resolve_marks(self, doc: ParsedDoc) -> list[SidecarPage | None]:
        """The sidecar page each of ``doc.page_marks`` stands for, in order.

        Where labels repeat, the label alone is not enough; the position in the
        text is. Markers run in page order, so each takes the first page carrying
        its label that lies after the page the previous marker took. A labelled
        page without a marker of its own (it had no text) is skipped rather than
        claimed, and a marker whose label the sidecar does not know -- book text
        that looks like one -- resolves to None and moves nothing.
        """
        out: list[SidecarPage | None] = []
        last_pos = 0
        for label, _offset in doc.page_marks:
            entry = next((p for p in self._by_label.get(label, []) if p.pos > last_pos), None)
            out.append(entry)
            if entry is not None:
                last_pos = entry.pos
        return out

    # the master, read once ---------------------------------------------

    @property
    def doc(self) -> ParsedDoc:
        """The master, parsed. Offsets of a ``Locus`` are offsets into its body."""
        if self._doc is None:
            self._doc = parse_prepared(self.text)
        return self._doc

    @property
    def headings(self) -> list[MasterHeading]:
        if self._headings is None:
            self._headings = master_headings(self.doc)
        return self._headings

    def _mark_index(self, label: str, occurrence: int) -> int | None:
        """Which page marker is the ``occurrence``-th to carry ``label``."""
        seen = 0
        for i, (lbl, _off) in enumerate(self.doc.page_marks):
            if lbl == label:
                seen += 1
                if seen == occurrence:
                    return i
        return None

    def _span_at(self, i: int) -> tuple[int, int]:
        """The body the i-th page marker addresses: from it to the next one."""
        marks = self.doc.page_marks
        end = marks[i + 1][1] if i + 1 < len(marks) else len(self.doc.body)
        return marks[i][1], end

    def _sidecar_at(self, i: int) -> SidecarPage | None:
        """The sidecar page the i-th marker stands for, where a sidecar says."""
        if not self.pages:
            return None
        if self._resolved is None:
            self._resolved = self.resolve_marks(self.doc)
        return self._resolved[i]

    def page_text(self, label: str, occurrence: int = 1) -> str | None:
        """The text of the ``occurrence``-th page printing ``label``.

        None where the master marks no such page -- then nothing can be looked
        up on it. Read from the markers alone; no sidecar is needed for this.
        """
        i = self._mark_index(label, occurrence)
        return None if i is None else self.doc.body[slice(*self._span_at(i))]

    def wording_at(self, offset: int, words: int = MIN_WORDING_WORDS) -> str | None:
        """A wording for an address beginning at ``offset``, or None.

        Blind to markers -- an anchor between two words is not a word -- and
        never past the end of its paragraph or past the next page marker. A
        wording that runs over a paragraph boundary breaks the moment someone
        puts a heading there (P-M2, Briefing §8), and one that runs over a page
        boundary is never found at all: ``locate`` reads one page and the rest
        of the wording stands on the next. Neither is a stale address; both are
        addresses that were cut badly. None where too few words stand between
        ``offset`` and the end of its paragraph or page.
        """
        body = self.doc.body
        para = body.find("\n\n", offset)
        end = len(body) if para < 0 else para
        page = next((off for _lbl, off in self.doc.page_marks if off > offset), None)
        if page is not None:
            end = min(end, page)
        # Read from the paragraph's start, so that a marker ``offset`` falls
        # inside is recognised as one: the wording then begins behind it rather
        # than with its tail ("52]{#p-52} entdeckt werden ...").
        before = body.rfind("\n\n", 0, offset)
        opens = 0 if before < 0 else before + 2
        clean, kept = blind(body[opens:end])
        first = next((i for i, p in enumerate(kept) if p + opens >= offset), len(clean))
        tokens = clean[first:].split()
        return " ".join(tokens[:words]) if len(tokens) >= words else None

    # resolving an address (spec §4.7) -----------------------------------

    def _search(self, i: int, needle: str) -> tuple[int, int, int] | None:
        """(start, end, how often) of ``needle`` on the i-th page, or None.

        Each page is blinded and normalized once and kept: resolving a volume's
        thousand addresses asks the same pages over and over.
        """
        if i not in self._searchable:
            clean, cmap = blind(self.doc.body[slice(*self._span_at(i))])
            norm, posmap = _normalized_with_map(clean)
            self._searchable[i] = (cmap, norm, posmap)
        cmap, norm, posmap = self._searchable[i]
        idx = norm.find(needle)
        if idx < 0:
            return None
        at = self._span_at(i)[0]
        return (at + cmap[posmap[idx]],
                at + cmap[posmap[idx + len(needle) - 1]] + 1,
                norm.count(needle))

    def _locus_at(self, i: int, needle: str, *, proposed: bool = False) -> Locus | None:
        hit = self._search(i, needle)
        if hit is None:
            return None
        label = self.doc.page_marks[i][0]
        entry = self._sidecar_at(i)
        return Locus(page=label,
                     occurrence=sum(1 for lbl, _ in self.doc.page_marks[:i + 1]
                                    if lbl == label),
                     pos=entry.pos if entry else None, start=hit[0], end=hit[1],
                     proposed=proposed, ambiguous=hit[2] > 1,
                     label_source=entry.source if entry else None)

    def locate(self, wording: str, page: str | None = None,
               occurrence: int = 1) -> Locus | None:
        """Where ``wording`` stands on the page the address names.

        With ``page``, the search is that page and nothing else: where the page
        no longer carries the wording the answer is None -- *stale* -- and the
        same words elsewhere in the volume are never taken instead (Befund
        §1.2). ``nearest`` may then propose another page, as a proposal.

        Without ``page``, the pages are read in order and the first hit answers;
        text in front of the first marker stands on no page and carries no
        address. An occurrence without a page names nothing, and is refused
        rather than quietly ignored. A wording under ``MIN_WORDING_WORDS`` words
        is refused too, and one the page prints twice answers ``ambiguous``
        rather than silently the first (P-M2, Briefing §8).
        """
        if page is None and occurrence != 1:
            raise ValueError("an occurrence belongs to a page; page is None")
        needle = _wording_of(wording)
        if page is not None:
            i = self._mark_index(page, occurrence)
            return None if i is None else self._locus_at(i, needle)
        for i in range(len(self.doc.page_marks)):
            found = self._locus_at(i, needle)
            if found is not None:
                return found
        return None

    def nearest(self, wording: str, page: str, occurrence: int = 1) -> Locus | None:
        """The nearest page around the address that does carry ``wording``.

        Spec §4.7: a consumer MAY offer it as a proposal. At most
        ``NEAREST_REACH`` pages in either direction, the page after before the
        page before at equal distance -- text that moves, moves forward.
        """
        needle = _wording_of(wording)
        i = self._mark_index(page, occurrence)
        if i is None:
            return None
        for step in range(1, NEAREST_REACH + 1):
            for j in (i + step, i - step):
                if 0 <= j < len(self.doc.page_marks):
                    found = self._locus_at(j, needle, proposed=True)
                    if found is not None:
                        return found
        return None

    # the section a position stands in ------------------------------------

    def _depths(self) -> list[int]:
        """The true depth of every '#' line of the master.

        The structure sidecar lists exactly these headings, in this order (spec
        §6.5), and knows the depths past the sixth that Markdown cannot spell;
        where it is missing, or lists other headings than this master prints,
        the hashes say what they can.
        """
        heads = self.headings
        if self.structure and len(self.structure.headings) == len(heads):
            return [n.depth for n in self.structure.headings]
        return [h.marks for h in heads]

    def section_span(self, page: str, title: str) -> tuple[int, int] | None:
        """The section the heading ``title`` opens on page ``page``.

        From the heading to the next of the same depth or shallower, as a span
        of ``doc.body``; to the end of the master where none follows. The
        heading is found by page and folded wording (``outline.fold``), so that
        OCR spacing and punctuation do not decide it. None where that page
        prints no such heading.
        """
        want = fold(title)
        heads = self.headings
        i = next((k for k, h in enumerate(heads)
                  if h.page == page and fold(h.text) == want), None)
        if i is None:
            return None
        depths = self._depths()
        for j in range(i + 1, len(heads)):
            if depths[j] <= depths[i]:
                return (heads[i].start, heads[j].start)
        return (heads[i].start, len(self.doc.body))

    def node_at(self, offset: int) -> MasterHeading | None:
        """The last heading at or before ``offset``; None in front of the first.

        A heading is its own node: a position on the heading line stands in the
        section it opens, not in the one before it.
        """
        found = None
        for h in self.headings:
            if h.start > offset:
                break
            found = h
        return found


def load_bundle(master_path: str | Path) -> Bundle | None:
    """The master at ``master_path`` with its declaration and its pagination sidecar.

    A master whose metadata block does not name a ``format_version`` is not a
    bundle -- a hand-written Markdown file, or one from before 0.2.0 -- and gets
    None: nothing here guesses which conventions it follows. A missing sidecar is
    no error (the text is whole without it, spec §3); a sidecar of a version this
    reader does not know is one, and is refused rather than half-read. Both
    sidecars, the pagination and the structure, are read by that same rule.
    """
    from scriptor.reflow.regions import read_metadata_block

    master = Path(master_path)
    text = master.read_text(encoding="utf-8")
    metadata = read_metadata_block(text)
    if not metadata or not metadata.get("format_version"):
        return None

    pages: list[SidecarPage] = []
    sidecar = master.with_name(master.name + ".pagination.json")
    if sidecar.exists():
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        version = payload.get("version")
        if version != SIDECAR_VERSION:
            raise ValueError(f"{sidecar}: unsupported pagination sidecar version {version!r}")
        pages = [
            SidecarPage(pos=p["pos"], label=p["label"], source=p["source"],
                        confidence=p.get("confidence"))
            for p in payload.get("pages", [])
        ]
    return Bundle(master=master, text=text, metadata=metadata, pages=pages,
                  structure=read_structure_sidecar(master))
