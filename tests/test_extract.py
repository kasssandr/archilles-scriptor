"""The pymupdf backend reads a text layer. It must never silently OCR.

A scanned book carries a full-page image *and* a text layer written by whatever
engine digitised it. pymupdf4llm's default (``OCRMode.SELECT_REMOVING_OLD``)
looks at such a page, sees an image covering it, and runs Tesseract over the
picture — while the existing layer stays. "Removing old" only removes spans it
recognises as previous OCR output; a FineReader layer is not one of those. The
page then carries every paragraph twice, once per engine, in two spellings.

For scriptor that is not a cosmetic defect: every footnote definition and every
marker would be duplicated, and the confidence layer would score glyphs that the
book never printed. Which engine turns pixels into text is a decision the caller
makes (``ocr_backend``), never one this backend takes on its own.
"""

from pathlib import Path

import pymupdf
import pytest

from scriptor.extract import pymupdf_backend

SCAN_TEXT = [
    "Vespasian had reached the throne by the same road,",
    "and the memory of it was not one the Flavians kept.",
    "Titus, his son, is said to have wept at the theatre.",
]


def _make_scanned_pdf(path: Path) -> None:
    """A page that is a picture of its own text, with the text layer on top."""
    src = pymupdf.open()
    page = src.new_page(width=300, height=400)
    for i, line in enumerate(SCAN_TEXT):
        page.insert_text((20, 60 + i * 20), line, fontsize=9)
    pix = page.get_pixmap(dpi=200)

    out = pymupdf.open()
    scan = out.new_page(width=300, height=400)
    scan.insert_image(scan.rect, pixmap=pix)
    for i, line in enumerate(SCAN_TEXT):
        scan.insert_text((20, 60 + i * 20), line, fontsize=9)
    out.save(path)


def test_extract_disables_ocr(tmp_path, monkeypatch):
    """The backend asks pymupdf4llm for the text layer and nothing else."""
    from pymupdf4llm.ocr import OCRMode

    seen = {}

    def spy(pdf, **kwargs):
        seen.update(kwargs)
        return [{"text": "page one"}]

    monkeypatch.setattr(pymupdf_backend.pymupdf4llm, "to_markdown", spy)
    pdf = tmp_path / "book.pdf"
    _make_scanned_pdf(pdf)

    pymupdf_backend.extract(pdf, tmp_path / "pages")

    assert seen["use_ocr"] == OCRMode.NEVER


@pytest.mark.skipif(
    pymupdf.get_tessdata() is None, reason="needs Tesseract to reproduce the double pass"
)
def test_scanned_page_is_not_extracted_twice(tmp_path):
    """A sentence printed once on the page appears once in the output."""
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    written = pymupdf_backend.extract(pdf, tmp_path / "pages")

    assert len(written) == 1
    text = " ".join(written[0].read_text(encoding="utf-8").split())
    assert text.count("Vespasian had reached the throne") == 1
