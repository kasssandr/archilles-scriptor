"""The reflow enters through the page model and says what it measured."""

from scriptor.page import Box, Line, Span, SourcePage, dumps
from scriptor.reflow.core import main


def _frag(text, x0, baseline):
    box = Box(x0, baseline - 7.0, x0 + 6 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=9.0)], box=box, baseline=baseline)


def _write(pages_dir, index, fragments, *, width=300.0):
    page = SourcePage(index=index, width=width, height=400.0, source="pymupdf",
                      lines=[_frag(*f) for f in fragments])
    (pages_dir / f"{index:08d}.json").write_text(dumps(page), encoding="utf-8")


def test_json_pages_are_reassembled_before_reflow(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    _write(pages_dir, 1, [
        ("Die Fragmente einer Zeile", 30, 50.0),
        ("gehoeren zusammen.", 190, 50.4),
    ])

    out = tmp_path / "book.txt"
    main(str(pages_dir), str(out))

    assert "Die Fragmente einer Zeile gehoeren zusammen." in out.read_text(
        encoding="utf-8"
    )


def test_measured_pages_are_reported(tmp_path, capsys):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    _write(pages_dir, 1, [("Ein schlichter Satz.", 30, 50.0)])

    main(str(pages_dir), str(tmp_path / "book.txt"))

    assert "1 of 1 pages reassembled from geometry" in capsys.readouterr().err


def test_txt_pages_still_work_and_report_no_measurement(tmp_path, capsys):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "00000001.txt").write_text("Ein schlichter Satz.\n", encoding="utf-8")

    out = tmp_path / "book.txt"
    main(str(pages_dir), str(out))

    assert "Ein schlichter Satz." in out.read_text(encoding="utf-8")
    assert "0 of 1 pages reassembled from geometry" in capsys.readouterr().err


def test_a_column_wide_gap_is_reported(tmp_path, capsys):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    _write(pages_dir, 1, [
        ("Kopfzeile", 30, 20.0),
        ("linke Spalte", 20, 100.0),
        ("rechte Spalte", 250, 100.0),
        ("Fusszeile", 30, 380.0),
    ])

    main(str(pages_dir), str(tmp_path / "book.txt"))

    err = capsys.readouterr().err
    assert "column-wide horizontal gap" in err


def _two_column_fragments(page, rows=12):
    """A page set the way Sen et al. is: two columns on one shared baseline grid.

    The page number sits in the text so the running-element stripper does not take
    the top line for a running head.
    """
    fragments = []
    for i in range(rows):
        y = 60.0 + i * 12.0
        fragments.append((f"Seite {page} linke Spalte Zeile {i} Text", 55.0, y))
        fragments.append((f"Seite {page} rechte Spalte Zeile {i} Text", 320.0, y))
    return fragments


def test_a_two_column_document_is_read_column_by_column(tmp_path, capsys):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for index in (1, 2, 3):
        _write(pages_dir, index, _two_column_fragments(index), width=612.0)

    out = tmp_path / "paper.txt"
    main(str(pages_dir), str(out))

    text = out.read_text(encoding="utf-8")
    assert "linke Spalte Zeile 0 Text Seite 1 rechte Spalte" not in text
    assert text.index("Seite 1 linke Spalte Zeile 11") < text.index(
        "Seite 1 rechte Spalte Zeile 0"
    )
    assert "Two-column layout: gutter at" in capsys.readouterr().err
