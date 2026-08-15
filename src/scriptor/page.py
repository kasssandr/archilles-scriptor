"""What a backend delivers: measured facts about one page, and nothing else.

A backend says where something sits and how big it is set. Whether it is a running
head, a footnote or a heading is decided later, in code that can be audited (README:
"Structure is decided deterministically"). A backend that classified for us would
decide the structure, and swapping the backend would silently change the output.

``Line`` is the line *as the backend reports it*. A Google Books scan splits one
printed line into several fragments, and LuraDocument hands over one fragment per
word. Assembling printed lines is a judgement -- blind clustering would join across
two columns -- and lives in ``reflow/textlines.py``.

``baseline`` is the anchor for that assembly, not ``box``. Within one printed line of
Seeck p.120 the box top scatters by 2.2 points, because words with ascenders sit
higher; the baseline scatters by 0.36. Clustering on the box tears the line apart.

Sources without geometry (Internet-Archive page TXT) produce the same type with every
measurement absent: one span per line, no boxes. Not a special case, just less
knowledge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Box:
    """PDF points, origin top left."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Span:
    """A run of characters the backend reports with uniform styling."""

    text: str
    box: Box | None = None
    size: float | None = None
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Glyph:
    """One character with its own box. Optional: most backends do not report it."""

    char: str
    box: Box
    confidence: float | None = None


@dataclass(frozen=True)
class Link:
    """A link that points somewhere inside this document.

    A measured fact, like a box: the file itself resolves the destination to a
    page, and ``target`` is that page's 1-based physical index. Links pointing
    out of the document (a URI) are not kept -- they say nothing about this
    volume.

    What it is *for* is decided later, as with everything a backend reports. On
    a contents page it is the producer stating where an entry goes, which is the
    question ``reflow/pagination`` otherwise answers by searching the text for a
    title.
    """

    box: Box
    target: int


@dataclass
class Line:
    spans: list[Span]
    box: Box | None = None
    baseline: float | None = None      # y of the script line; see module docstring
    confidence: float | None = None
    glyphs: list[Glyph] | None = None

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def size(self) -> float | None:
        """The dominant size, weighted by how many characters carry it.

        An OCR text layer *estimates* the size from glyph height, so the values
        scatter -- Berliner shows 128 distinct sizes on five pages, with an
        interquartile range of 5.6 points. Callers must cluster with a tolerance
        rather than compare for equality. Ties go to the larger size, so the result
        does not depend on dict ordering.
        """
        weights: dict[float, int] = {}
        for span in self.spans:
            if span.size is None:
                continue
            weights[span.size] = weights.get(span.size, 0) + len(span.text)
        if not weights:
            return None
        return max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0]


@dataclass
class SourcePage:
    index: int                          # physical page, 1-based file ordinal
    lines: list[Line] = field(default_factory=list)
    width: float | None = None
    height: float | None = None
    source: str = ""                    # backend name, for reproducibility
    # The printed page label as the document's own catalogue states it (PDF
    # PageLabels: "xiv", "36"). A measured fact like a box, not a judgement —
    # whether to *believe* it against the printed pages is reflow's decision.
    label: str | None = None
    # Links from this page into the document. Empty where none were measured —
    # which includes every page model written before this field existed.
    links: list[Link] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


# ----------------------------------------------------------------------
# JSON. Absent measurements are omitted, never written as null: a missing key
# says "nothing was measured here", which ``null`` would blur into "measured,
# and it was nothing".
# ----------------------------------------------------------------------

def _box_out(box: Box) -> list[float]:
    return [box.x0, box.y0, box.x1, box.y1]


def _box_in(raw) -> Box | None:
    return None if raw is None else Box(*raw)


def _span_out(span: Span) -> dict:
    out: dict = {"text": span.text}
    if span.box is not None:
        out["box"] = _box_out(span.box)
    if span.size is not None:
        out["size"] = span.size
    if span.bold:
        out["bold"] = True
    if span.italic:
        out["italic"] = True
    return out


def _span_in(raw: dict) -> Span:
    return Span(
        text=raw["text"],
        box=_box_in(raw.get("box")),
        size=raw.get("size"),
        bold=raw.get("bold", False),
        italic=raw.get("italic", False),
    )


def _glyph_out(glyph: Glyph) -> dict:
    out: dict = {"char": glyph.char, "box": _box_out(glyph.box)}
    if glyph.confidence is not None:
        out["confidence"] = glyph.confidence
    return out


def _glyph_in(raw: dict) -> Glyph:
    return Glyph(char=raw["char"], box=_box_in(raw["box"]),
                 confidence=raw.get("confidence"))


def _line_out(line: Line) -> dict:
    out: dict = {"spans": [_span_out(s) for s in line.spans]}
    if line.box is not None:
        out["box"] = _box_out(line.box)
    if line.baseline is not None:
        out["baseline"] = line.baseline
    if line.confidence is not None:
        out["confidence"] = line.confidence
    if line.glyphs is not None:
        out["glyphs"] = [_glyph_out(g) for g in line.glyphs]
    return out


def _line_in(raw: dict) -> Line:
    glyphs = raw.get("glyphs")
    return Line(
        spans=[_span_in(s) for s in raw["spans"]],
        box=_box_in(raw.get("box")),
        baseline=raw.get("baseline"),
        confidence=raw.get("confidence"),
        glyphs=[_glyph_in(g) for g in glyphs] if glyphs is not None else None,
    )


def _link_out(link: Link) -> dict:
    return {"box": _box_out(link.box), "target": link.target}


def _link_in(raw: dict) -> Link:
    return Link(box=_box_in(raw["box"]), target=raw["target"])


def to_dict(page: SourcePage) -> dict:
    out: dict = {"version": SCHEMA_VERSION, "index": page.index}
    if page.source:
        out["source"] = page.source
    if page.width is not None:
        out["width"] = page.width
    if page.height is not None:
        out["height"] = page.height
    if page.label is not None:
        out["label"] = page.label
    if page.links:
        out["links"] = [_link_out(link) for link in page.links]
    out["lines"] = [_line_out(line) for line in page.lines]
    return out


def from_dict(payload: dict) -> SourcePage:
    version = payload.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported page schema version {version!r}")
    return SourcePage(
        index=payload["index"],
        lines=[_line_in(line) for line in payload.get("lines", [])],
        width=payload.get("width"),
        height=payload.get("height"),
        source=payload.get("source", ""),
        label=payload.get("label"),
        links=[_link_in(raw) for raw in payload.get("links", [])],
    )


def dumps(page: SourcePage) -> str:
    """Stable JSON, so a page diffs cleanly in version control."""
    return json.dumps(to_dict(page), indent=1, ensure_ascii=False) + "\n"


def loads(text: str) -> SourcePage:
    return from_dict(json.loads(text))


# ----------------------------------------------------------------------
# Loading a pages directory
# ----------------------------------------------------------------------

def page_from_text(index: int, text: str) -> SourcePage:
    """Lift a plain page TXT into the model: one span per line, no geometry.

    Blank lines are kept as empty lines -- ``reflow.parse_page`` reads them as
    paragraph breaks, so dropping them would silently merge paragraphs.
    """
    return SourcePage(
        index=index,
        lines=[Line(spans=[Span(line)] if line else []) for line in text.splitlines()],
        source="text",
    )


def load_pages(src: str | Path) -> list[SourcePage]:
    """Read a pages directory: JSON when present, else legacy page TXT.

    A directory holding both formats for the same page is an error, not a question
    of precedence. Whichever we picked, the user would never learn that the other
    file existed and differed (README: "Never guess silently"). The text channel
    that ``extract --emit-txt`` writes lives in a ``txt/`` subdirectory, which this
    glob does not reach.
    """
    src = Path(src)
    jsons = sorted(src.glob("[0-9]*.json"))
    txts = sorted(src.glob("[0-9]*.txt"))

    clash = sorted({p.stem for p in jsons} & {p.stem for p in txts})
    if clash:
        raise ValueError(
            f"{src}: pages {', '.join(clash)} exist as both .json and .txt; "
            f"remove one -- refusing to choose"
        )

    if jsons:
        return [loads(p.read_text(encoding="utf-8")) for p in jsons]
    return [
        page_from_text(i, p.read_text(encoding="utf-8", errors="replace"))
        for i, p in enumerate(txts, start=1)
    ]
