"""PDF text extraction via pymupdf4llm.

Writes one TXT file per page into ``out_dir`` with zero-padded filenames
(``00000001.txt`` …) so the reflow stage can ingest them in order.

For now we use the plain ``to_markdown(page_chunks=True)`` path and write
the per-chunk ``text`` field. A2 (using the rich dict with ``page_boxes``
and fonts) is deferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pymupdf4llm


def extract(pdf_path: str | Path, out_dir: str | Path) -> list[Path]:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    written: list[Path] = []
    for i, chunk in enumerate(_iter_text(chunks), start=1):
        name = f"{i:08d}.txt"
        path = out_dir / name
        path.write_text(chunk, encoding="utf-8")
        written.append(path)
    return written


def _iter_text(chunks: Iterable) -> Iterable[str]:
    for c in chunks:
        if isinstance(c, dict):
            yield c.get("text", "")
        else:
            yield str(c)
