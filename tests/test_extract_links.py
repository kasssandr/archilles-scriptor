"""The backend reports the links it measured, and only the internal ones.

Measured on the corpus: of eighteen volumes exactly one carries links from its
contents into the book (Libros, 2307 of them), one carries links from note
markers to the note section (Le radici, 682), and the rest carry external URIs
or nothing. Where they exist they are the producer's own statement of where an
entry goes -- there is no more direct evidence about a page reference in a PDF.
"""

from pathlib import Path

import pymupdf

from scriptor.extract import pymupdf_backend


def _linked_pdf(path: Path) -> None:
    """Three pages; the first carries a contents line linking to the third."""
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=300, height=400)
        page.insert_text((20, 60), f"Seite {i + 1}", fontsize=9)
    contents = doc[0]
    contents.insert_text((20, 100), "Kapitel 1 .......... 31", fontsize=9)
    contents.insert_link({
        "kind": pymupdf.LINK_GOTO,
        "from": pymupdf.Rect(20, 90, 200, 105),
        "page": 2,                       # 0-based: the third page
    })
    contents.insert_link({
        "kind": pymupdf.LINK_URI,
        "from": pymupdf.Rect(20, 200, 200, 215),
        "uri": "https://example.org",
    })
    doc.save(path)
    doc.close()


def test_an_internal_link_is_reported_with_its_target(tmp_path):
    pdf = tmp_path / "linked.pdf"
    _linked_pdf(pdf)
    pages = pymupdf_backend.read_pages(pdf) if hasattr(
        pymupdf_backend, "read_pages") else None
    if pages is None:
        doc = pymupdf.open(pdf)
        pages = [pymupdf_backend.read_page(p, i)
                 for i, p in enumerate(doc, start=1)]
        doc.close()
    (link,) = pages[0].links
    assert link.target == 3          # 1-based physical page
    assert link.box.x0 == 20.0


def test_a_link_out_of_the_document_is_not_reported(tmp_path):
    # A URI says nothing about this volume's pagination.
    pdf = tmp_path / "linked.pdf"
    _linked_pdf(pdf)
    doc = pymupdf.open(pdf)
    page = pymupdf_backend.read_page(doc[0], 1)
    doc.close()
    assert len(page.links) == 1


def test_a_page_without_links_reports_none(tmp_path):
    pdf = tmp_path / "linked.pdf"
    _linked_pdf(pdf)
    doc = pymupdf.open(pdf)
    page = pymupdf_backend.read_page(doc[1], 2)
    doc.close()
    assert page.links == []
