"""The reflow enters through the page model and says what it measured."""

from scriptor.page import Box, Line, Span, SourcePage, dumps
from scriptor.reflow.core import main


def _frag(text, x0, baseline):
    box = Box(x0, baseline - 7.0, x0 + 6 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=9.0)], box=box, baseline=baseline)


def _write(pages_dir, index, fragments):
    page = SourcePage(index=index, width=300.0, height=400.0, source="pymupdf",
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
