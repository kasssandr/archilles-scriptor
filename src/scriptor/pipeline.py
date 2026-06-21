"""End-to-end orchestration: PDF -> per-page TXT -> Markdown/TXT."""

from __future__ import annotations

from pathlib import Path

from scriptor.extract import pymupdf_backend
from scriptor.reflow.core import main as reflow_main


def extract(pdf_path: str | Path, out_dir: str | Path) -> list[Path]:
    return pymupdf_backend.extract(pdf_path, out_dir)


def reflow(src_dir: str | Path, out_path: str | Path, fmt: str | None = None) -> None:
    reflow_main(str(src_dir), str(out_path), fmt)


def run_all(
    pdf_path: str | Path,
    out_path: str | Path,
    fmt: str | None = None,
    pages_dir: str | Path | None = None,
) -> None:
    pdf_path = Path(pdf_path)
    out_path = Path(out_path)
    if pages_dir is None:
        pages_dir = out_path.parent / f"{out_path.stem}_pages"
    extract(pdf_path, pages_dir)
    reflow(pages_dir, out_path, fmt)


def translate_prep(master_path: str | Path, out_path: str | Path) -> Path:
    """Master-Markdown -> übersetzungsreifes MD + Briefing-Sidecar.
    Gibt den Pfad des Briefing-Sidecars zurück."""
    from scriptor.reflow.translation import prepare_translation, BRIEFING

    master_path = Path(master_path)
    out_path = Path(out_path)
    md = master_path.read_text(encoding="utf-8")
    out_path.write_text(prepare_translation(md), encoding="utf-8")
    briefing_path = out_path.with_name(out_path.stem + ".briefing.txt")
    briefing_path.write_text(BRIEFING, encoding="utf-8")
    return briefing_path
