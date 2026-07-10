"""The PDF catalogue's page labels: measured by the backend, verified by reflow.

A PDF may carry the printed page label of every physical page in its catalogue
(PageLabels: roman frontmatter, arabic main text). Zuckerman does — physical
page 56 is printed "36" — and precisely where the printed-label heuristic must
guess (a chapter opening shows no running head, only the big chapter number,
which the detector read as the label), the catalogue simply knows.

Catalogue labels can also be wrong: scan tooling generates them mechanically.
So reflow never trusts the column blindly — it must agree with the labels
actually detected on the printed pages before it wins.
"""

import json

import pymupdf

from scriptor.extract import pymupdf_backend
from scriptor.page import SourcePage, loads, page_from_text
from scriptor.reflow.core import Page, reconcile_page_numbers


# ----------------------------------------------------------------------
# the backend measures the label
# ----------------------------------------------------------------------

def _pdf_with_labels(path):
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=300, height=400)
        page.insert_text((20, 60), f"Seite {i} Inhalt.", fontsize=9)
    doc.set_page_labels([
        {"startpage": 0, "prefix": "", "firstpagenum": 1, "style": "r"},
        {"startpage": 1, "prefix": "", "firstpagenum": 5, "style": "D"},
    ])
    doc.save(path)


def test_extract_writes_the_catalogue_label(tmp_path):
    pdf = tmp_path / "buch.pdf"
    _pdf_with_labels(pdf)
    out = tmp_path / "pages"
    pymupdf_backend.extract(pdf, out)

    labels = [
        json.loads((out / f"{i:08d}.json").read_text(encoding="utf-8")).get("label")
        for i in (1, 2, 3)
    ]
    assert labels == ["i", "5", "6"]


def test_extract_omits_the_label_where_the_pdf_has_none(tmp_path):
    pdf = tmp_path / "buch.pdf"
    doc = pymupdf.open()
    doc.new_page(width=300, height=400).insert_text((20, 60), "Text.", fontsize=9)
    doc.save(pdf)
    out = tmp_path / "pages"
    pymupdf_backend.extract(pdf, out)

    payload = json.loads((out / "00000001.json").read_text(encoding="utf-8"))
    assert "label" not in payload


def test_the_label_survives_the_json_round_trip():
    page = SourcePage(index=7, label="xiv")
    from scriptor.page import dumps
    assert loads(dumps(page)).label == "xiv"


def test_text_pages_carry_no_label():
    assert page_from_text(1, "nur Text\n").label is None


# ----------------------------------------------------------------------
# reflow verifies the column before it wins
# ----------------------------------------------------------------------

def _page(top, backend):
    p = Page(num=-1, body_lines=["Etwas Text auf der Seite."], label_top=top)
    p.backend_label = backend
    return p


def test_verified_backend_labels_fill_the_gap_the_heuristic_misread():
    # Four pages agree with the catalogue; on the chapter opening the detector
    # read the big chapter number "2" where the catalogue knows "36".
    pages = [
        _page("33", "33"), _page("34", "34"), _page("35", "35"),
        _page("2", "36"),
        _page("37", "37"), _page("38", "38"),
    ]
    col = reconcile_page_numbers(pages)
    assert "backend" in col
    assert [p.label for p in pages] == ["33", "34", "35", "36", "37", "38"]


def test_a_contradicting_backend_column_is_ignored():
    # A mechanically generated catalogue (physical = printed) over a book whose
    # printed labels start at 33: no agreement, the heuristic stands.
    pages = [_page(str(33 + i), str(1 + i)) for i in range(6)]
    col = reconcile_page_numbers(pages)
    assert "backend" not in col
    assert [p.label for p in pages] == [str(33 + i) for i in range(6)]


def test_pages_without_a_backend_label_keep_the_detected_one():
    pages = [
        _page("33", "33"), _page("34", "34"), _page("35", "35"), _page("36", None),
    ]
    reconcile_page_numbers(pages)
    assert [p.label for p in pages] == ["33", "34", "35", "36"]


def test_without_any_backend_labels_the_behaviour_is_unchanged():
    pages = [_page("33", None), _page("34", None), _page("35", None)]
    col = reconcile_page_numbers(pages)
    assert col == "top"
    assert [p.label for p in pages] == ["33", "34", "35"]
