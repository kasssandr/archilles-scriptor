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


def bind_footnotes(in_path: str | Path, out_path: str | Path):
    """DOCX -> DOCX mit angehängten Fußnoten + Report-Sidecar.
    Gibt den BindReport zurück."""
    from scriptor.docx.document import Document
    from scriptor.docx.footnotes import bind

    in_path = Path(in_path)
    out_path = Path(out_path)
    doc = Document.load(in_path)
    report = bind(doc)
    doc.save(out_path)

    lines = [
        f"# Fußnoten-Binde-Report für {out_path.name}",
        f"# {len(report.attached)} angehängt, {len(report.orphan_defs)} "
        f"verwaiste Definitionen, {len(report.orphan_refs)} Referenzen ohne Definition.",
        "",
    ]
    for n, idx in report.attached:
        lines.append(f"angehängt:  FN {n}  (Referenz in Absatz {idx})")
    for n, idx in report.orphan_defs:
        lines.append(f"verwaiste Definition:  FN {n}  (Absatz {idx})")
    for n, idx in report.orphan_refs:
        lines.append(f"Referenz ohne Definition:  FN {n}  (Absatz {idx})")
    log_path = out_path.with_name(out_path.name + ".bind-log.txt")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


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
