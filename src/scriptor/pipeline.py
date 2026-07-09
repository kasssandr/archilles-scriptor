"""End-to-end orchestration: PDF -> per-page TXT -> Markdown/TXT."""

from __future__ import annotations

from pathlib import Path

from scriptor._text import plural
from scriptor.extract import pymupdf_backend
from scriptor.reflow.core import main as reflow_main


def extract(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    emit_txt: bool = False,
) -> list[Path]:
    return pymupdf_backend.extract(pdf_path, out_dir, emit_txt=emit_txt)


def reflow(
    src_dir: str | Path,
    out_path: str | Path,
    fmt: str | None = None,
    decisions: str | Path | None = None,
    ocr_profile: str | Path | None = None,
) -> None:
    reflow_main(
        str(src_dir),
        str(out_path),
        fmt,
        str(decisions) if decisions else None,
        str(ocr_profile) if ocr_profile else None,
    )


def run_all(
    pdf_path: str | Path,
    out_path: str | Path,
    fmt: str | None = None,
    pages_dir: str | Path | None = None,
    decisions: str | Path | None = None,
    ocr_profile: str | Path | None = None,
) -> None:
    pdf_path = Path(pdf_path)
    out_path = Path(out_path)
    if pages_dir is None:
        pages_dir = out_path.parent / f"{out_path.stem}_pages"
    extract(pdf_path, pages_dir)
    reflow(pages_dir, out_path, fmt, decisions, ocr_profile)


def bind_footnotes(in_path: str | Path, out_path: str | Path):
    """DOCX -> DOCX with attached footnotes + report sidecar.
    Returns the BindReport."""
    from scriptor.docx.document import Document
    from scriptor.docx.footnotes import bind

    in_path = Path(in_path)
    out_path = Path(out_path)
    doc = Document.load(in_path)
    report = bind(doc)
    doc.save(out_path)

    # A single list sorted by running paragraph number, so the document can be
    # walked linearly front to back in LibreOffice/Word. Each line carries a
    # searchable text snippet, since the paragraph number itself isn't visible
    # there. Follow-up cases (⚠) can be filtered out via full-text search.
    entries: list[tuple[int, int, str, str]] = (
        [(idx, n, "attached", s) for idx, n, s in report.attached]
        + [(idx, n, "! ORPHANED DEFINITION", s) for idx, n, s in report.orphan_defs]
        + [(idx, n, "! REFERENCE WITHOUT DEFINITION", s) for idx, n, s in report.orphan_refs]
    )
    entries.sort()
    lines = [
        f"# Footnote binding report for {out_path.name}",
        f"# {len(report.attached)} attached, "
        f"{plural(len(report.orphan_defs), 'orphaned definition')}, "
        f"{plural(len(report.orphan_refs), 'reference without a definition', 'references without a definition')}.",
        "# Sorted by paragraph number. Search for the snippet in »…« to find the passage.",
        "",
    ]
    for idx, n, label, snip in entries:
        lines.append(f"Paragraph {idx:>4} · FN {n:>3} · {label} · »{snip}«")
    log_path = out_path.with_name(out_path.name + ".bind-log.txt")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def translate_prep(master_path: str | Path, out_path: str | Path) -> Path:
    """Master Markdown -> translation-ready MD + briefing sidecar.
    Returns the path of the briefing sidecar."""
    from scriptor.reflow.translation import prepare_translation, BRIEFING

    master_path = Path(master_path)
    out_path = Path(out_path)
    md = master_path.read_text(encoding="utf-8")
    out_path.write_text(prepare_translation(md), encoding="utf-8")
    briefing_path = out_path.with_name(out_path.stem + ".briefing.txt")
    briefing_path.write_text(BRIEFING, encoding="utf-8")
    return briefing_path


def learn(decision_paths: list[Path], out_path: str | Path):
    """Build an OCR profile from decision sidecars. Pure: same files, same profile."""
    from scriptor.reflow import profile as profile_mod

    sources = [(p.name, Path(p).read_text(encoding="utf-8")) for p in decision_paths]
    prof = profile_mod.learn(sources)
    profile_mod.save(prof, out_path)
    return prof
