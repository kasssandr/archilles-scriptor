"""The pymupdf backend reports what it measured. It never OCRs.

A scanned book carries a full-page image and a text layer from whatever engine
digitised it. Turning pixels into text is the OCR backend's job, chosen by the
caller -- not something the extraction path does on its own. Two real books show
why a library that decides for itself is dangerous: Zuckerman's FineReader layer
is rendered visibly, so pymupdf4llm's default re-OCRed the page image and appended
the result; Susa and Thil-Lorrain carry an invisible OCR layer, which the same
default deletes and replaces, in the default language, over a French text.
"""

import json
from pathlib import Path

import pymupdf

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


def _make_image_only_pdf(path: Path) -> None:
    src = pymupdf.open()
    page = src.new_page(width=300, height=400)
    page.insert_text((20, 60), "nothing readable without OCR", fontsize=9)
    pix = page.get_pixmap(dpi=200)

    out = pymupdf.open()
    scan = out.new_page(width=300, height=400)
    scan.insert_image(scan.rect, pixmap=pix)
    out.save(path)


def _spans(payload: dict) -> list[dict]:
    return [span for line in payload["lines"] for span in line["spans"]]


def test_scanned_page_is_not_extracted_twice(tmp_path):
    """A sentence printed once on the page appears once in the model."""
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    written = pymupdf_backend.extract(pdf, tmp_path / "pages")

    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    text = " ".join(span["text"] for span in _spans(payload))
    assert text.count("Vespasian had reached the throne") == 1


def test_image_only_pdf_yields_empty_pages_and_says_so(tmp_path, capsys):
    pdf = tmp_path / "image.pdf"
    _make_image_only_pdf(pdf)

    written = pymupdf_backend.extract(pdf, tmp_path / "pages")

    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["lines"] == []
    err = capsys.readouterr().err
    assert "1 of 1 pages carry no text layer" in err
    assert "does not OCR" in err


def test_extracted_json_carries_geometry_and_no_markdown(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    written = pymupdf_backend.extract(pdf, tmp_path / "pages")
    payload = json.loads(written[0].read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["source"] == "pymupdf"
    assert payload["width"] == 300.0
    assert payload["height"] == 400.0

    first_line = payload["lines"][0]
    assert len(first_line["box"]) == 4
    assert first_line["baseline"] > 0
    assert len(first_line["spans"][0]["box"]) == 4
    assert first_line["spans"][0]["size"] > 0

    joined = " ".join(span["text"] for span in _spans(payload))
    assert "##" not in joined
    assert "**" not in joined
    assert "_" not in joined


def test_baseline_is_the_script_line_not_the_box_top(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    payload = json.loads(
        pymupdf_backend.extract(pdf, tmp_path / "pages")[0].read_text(encoding="utf-8")
    )
    line = payload["lines"][0]
    top, bottom = line["box"][1], line["box"][3]
    assert top < line["baseline"] <= bottom


def test_emit_txt_writes_a_subdirectory_that_load_pages_ignores(tmp_path):
    from scriptor.page import load_pages

    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)
    pages_dir = tmp_path / "pages"

    pymupdf_backend.extract(pdf, pages_dir, emit_txt=True)

    txt = (pages_dir / "txt" / "00000001.txt").read_text(encoding="utf-8")
    assert "Vespasian" in txt
    assert [p.index for p in load_pages(pages_dir)] == [1]


def test_glyph_trail_is_off_by_default_and_can_be_asked_for(tmp_path):
    pdf = tmp_path / "scan.pdf"
    _make_scanned_pdf(pdf)

    plain = json.loads(
        pymupdf_backend.extract(pdf, tmp_path / "a")[0].read_text(encoding="utf-8")
    )
    assert "glyphs" not in plain["lines"][0]

    rich = json.loads(
        pymupdf_backend.extract(pdf, tmp_path / "b", glyphs=True)[0].read_text(
            encoding="utf-8"
        )
    )
    glyphs = rich["lines"][0]["glyphs"]
    assert len(glyphs) > 0
    assert glyphs[0]["char"] == "V"
    # rawdict spans carry `chars`, not `text` -- the text must survive that
    assert rich["lines"][0]["spans"][0]["text"].startswith("Vespasian")
