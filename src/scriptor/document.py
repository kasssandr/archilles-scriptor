"""Reading a prepared document -- the format's reference consumer.

``parse_prepared`` reads spec-conform prepared Markdown (PREPARED_FORMAT_SPEC):
the metadata block is dropped, region, page and footnote markers, flags and
citation spans are read, all with offsets into the remaining text. The reach
rule a consumer needs on top of that -- which page and which region a position
is in -- is ``page_at`` and ``region_at``.

``load_bundle`` adds what travels beside the master (spec §3, §6.3): the fields
of the metadata block and the pagination sidecar, which carries the physical page
and the witness behind each label.

The reader lived in ``eval/``, the benchmark's workshop, where no consumer may
import from. Here it is the one place that knows the grammar; the benchmark and
archilles both read through it rather than keeping a copy.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from scriptor.reflow.pagelabel import PAGE_MARKER_RE
from scriptor.reflow.pagination.report import SIDECAR_VERSION

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


# the bundle --------------------------------------------------------------

@dataclass(frozen=True)
class SidecarPage:
    """One position of the pagination sidecar (spec §6.3)."""
    pos: int                       # physical page, 1-based
    label: str                     # as printed, verbatim
    source: str                    # the strongest witness; unknown values kept as they are
    confidence: float | None = None


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

    def __post_init__(self) -> None:
        self.pages = sorted(self.pages, key=lambda p: p.pos)
        self._by_label: dict[str, list[SidecarPage]] = {}
        for p in self.pages:
            self._by_label.setdefault(p.label, []).append(p)

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


def load_bundle(master_path: str | Path) -> Bundle | None:
    """The master at ``master_path`` with its declaration and its pagination sidecar.

    A master whose metadata block does not name a ``format_version`` is not a
    bundle -- a hand-written Markdown file, or one from before 0.2.0 -- and gets
    None: nothing here guesses which conventions it follows. A missing sidecar is
    no error (the text is whole without it, spec §3); a sidecar of a version this
    reader does not know is one, and is refused rather than half-read.
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
    return Bundle(master=master, text=text, metadata=metadata, pages=pages)
