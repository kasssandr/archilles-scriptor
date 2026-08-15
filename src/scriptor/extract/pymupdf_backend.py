"""PDF extraction via PyMuPDF's own text dictionary.

Writes one JSON file per page into ``out_dir`` with zero-padded filenames
(``00000001.json`` …) so the reflow stage can ingest them in order.

This backend reads the text layer a PDF already carries. It does not OCR. That is
not a limitation, it is the contract: which engine turns pixels into text is the
caller's decision (``extract/ocr_backend.py``). Two real books show why a library
that decides for itself is dangerous. Zuckerman's FineReader layer is rendered
*visibly*, so ``pymupdf4llm``'s default re-OCRed the page image and appended the
result -- every paragraph, footnote and marker twice. Susa and Thil-Lorrain carry
an *invisible* OCR layer, which the same default deletes and replaces, in the
default language, over a French text.

We read ``page.get_text("dict")``: blocks, lines, spans, each with ``bbox``,
``size``, ``font``, ``flags`` and ``origin``. Lines arrive in content-stream order
and are **not** sorted here -- reading order across columns is a judgement, and
judgements belong in scriptor code (``reflow/textlines.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

from scriptor.page import Box, Glyph, Line, Link, SourcePage, Span, dumps

_BOLD = 16      # span["flags"] bit 4
_ITALIC = 2     # span["flags"] bit 1


def _box(raw) -> Box:
    return Box(*(round(float(v), 2) for v in raw))


def _span_text(raw: dict) -> str:
    """``dict`` spans carry ``text``; ``rawdict`` spans carry ``chars`` instead."""
    if "text" in raw:
        return raw["text"]
    return "".join(c["c"] for c in raw.get("chars", ()))


def _span(raw: dict) -> Span:
    return Span(
        text=_span_text(raw),
        box=_box(raw["bbox"]),
        size=round(float(raw["size"]), 2),
        bold=bool(raw["flags"] & _BOLD),
        italic=bool(raw["flags"] & _ITALIC),
    )


def _glyphs(raw_line: dict) -> list[Glyph]:
    return [
        Glyph(char=c["c"], box=_box(c["bbox"]))
        for span in raw_line["spans"]
        for c in span.get("chars", ())
    ]


def _links(page: pymupdf.Page) -> list[Link]:
    """The links that point somewhere inside this document.

    A URI is dropped: it says nothing about this volume's pagination. What
    remains has to name a page, and pymupdf reports that in ``page`` -- as an
    int for a plain GoTo, and as a string for a named destination it resolved
    (Libros' contents links come through that way). A name it could *not*
    resolve arrives as a string that is not a number, and is dropped: an
    unresolved name is not a page reference.

    Reported 1-based, like ``SourcePage.index``, because everything downstream
    counts pages that way. pymupdf counts from zero.
    """
    out: list[Link] = []
    for raw in page.get_links():
        if raw.get("kind") not in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
            continue
        target = raw.get("page")
        if isinstance(target, str):
            target = int(target) - 1 if target.strip().isdigit() else None
        if target is None or target < 0:
            continue
        rect = raw.get("from")
        if rect is None:
            continue
        out.append(Link(box=_box(rect), target=target + 1))
    return out


def read_page(page: pymupdf.Page, index: int, *, glyphs: bool = False) -> SourcePage:
    """One page of the model. ``glyphs`` costs roughly twenty times the size."""
    raw = page.get_text("rawdict" if glyphs else "dict")
    lines: list[Line] = []
    for block in raw["blocks"]:
        if block.get("type") != 0:      # 0 = text, 1 = image
            continue
        for raw_line in block["lines"]:
            spans = [_span(s) for s in raw_line["spans"] if _span_text(s)]
            if not spans:
                continue
            # The baseline of the first span. Within a line all spans share it,
            # and it is what reflow/textlines.py clusters on -- the box top moves
            # with the ascenders of the words that happen to stand in the line.
            baseline = round(float(raw_line["spans"][0]["origin"][1]), 2)
            lines.append(
                Line(
                    spans=spans,
                    box=_box(raw_line["bbox"]),
                    baseline=baseline,
                    glyphs=_glyphs(raw_line) if glyphs else None,
                )
            )
    # The catalogue's printed label for this page (PDF PageLabels). An empty
    # string means the PDF declares none — omitted then, never invented.
    label = page.get_label()
    return SourcePage(
        index=index,
        lines=lines,
        width=round(page.rect.width, 2),
        height=round(page.rect.height, 2),
        source="pymupdf",
        label=label or None,
        links=_links(page),
    )


def extract(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    emit_txt: bool = False,
    glyphs: bool = False,
) -> list[Path]:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    blank = 0
    with pymupdf.open(pdf_path) as doc:
        # The catalogue's outline: chapter titles with their physical start
        # page. A measured fact, written as a sidecar; whether to believe it
        # is reflow's decision (reflow/outline.py: credibility + per-page
        # confirmation).
        from scriptor.reflow.outline import OutlineEntry, save_outline
        save_outline(
            [
                OutlineEntry(level=level, title=title.strip(), page=page)
                for level, title, page in doc.get_toc()
                if page >= 1
            ],
            out_dir,
        )
        for index, page in enumerate(doc, start=1):
            source_page = read_page(page, index, glyphs=glyphs)
            path = out_dir / f"{index:08d}.json"
            path.write_text(dumps(source_page), encoding="utf-8")
            written.append(path)
            if not source_page.lines:
                blank += 1
            if emit_txt:
                # A derived channel for human eyes, in its own directory: written
                # beside the JSON it would collide with it, and load_pages refuses
                # to choose between two files for one page.
                txt_dir = out_dir / "txt"
                txt_dir.mkdir(exist_ok=True)
                (txt_dir / f"{index:08d}.txt").write_text(
                    source_page.text + "\n", encoding="utf-8"
                )

    # A page without a text layer is not an empty page -- it is a page this backend
    # cannot read. Say so, rather than handing the reflow stage a file that looks
    # like a plate or a blank leaf. Sigilla Veri: 606 of 606.
    if blank:
        print(
            f"{blank} of {len(written)} pages carry no text layer. "
            f"This backend does not OCR; a scan needs an OCR backend.",
            file=sys.stderr,
        )
    return written
