"""PDF text extraction via pymupdf4llm.

Writes one TXT file per page into ``out_dir`` with zero-padded filenames
(``00000001.txt`` …) so the reflow stage can ingest them in order.

For now we use the plain ``to_markdown(page_chunks=True)`` path and write
the per-chunk ``text`` field. A2 (using the rich dict with ``page_boxes``
and fonts) is deferred.

This backend reads the text layer a PDF already carries. It does not OCR, and
the default would: pymupdf4llm sees the full-page image of a scan, decides the
page "needs OCR", and inserts a second text layer beside the first. Its removal
pass only strips spans it recognises as earlier OCR output, which a FineReader
or ABBYY layer is not — so every paragraph, every footnote definition and every
marker arrives twice, in two spellings. Turning pixels into text is the OCR
backend's job (``extract/ocr_backend.py``), chosen by the caller.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import pymupdf4llm
from pymupdf4llm.ocr import OCRMode


def extract(pdf_path: str | Path, out_dir: str | Path) -> list[Path]:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = pymupdf4llm.to_markdown(
        str(pdf_path), page_chunks=True, use_ocr=OCRMode.NEVER
    )
    written: list[Path] = []
    blank = 0
    for i, chunk in enumerate(_iter_text(chunks), start=1):
        name = f"{i:08d}.txt"
        path = out_dir / name
        path.write_text(chunk, encoding="utf-8")
        written.append(path)
        if not chunk.strip():
            blank += 1

    # A page without a text layer is not an empty page — it is a page this
    # backend cannot read. Say so, rather than handing the reflow stage a file
    # that looks like a plate or a blank leaf.
    if blank:
        print(
            f"{blank} of {len(written)} pages carry no text layer. "
            f"This backend does not OCR; a scan needs an OCR backend.",
            file=sys.stderr,
        )
    return written


def _iter_text(chunks: Iterable) -> Iterable[str]:
    for c in chunks:
        if isinstance(c, dict):
            yield c.get("text", "")
        else:
            yield str(c)
