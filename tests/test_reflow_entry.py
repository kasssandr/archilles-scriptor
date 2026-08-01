"""The reflow enters through the page model and says what it measured."""

from scriptor.page import Box, Line, Span, SourcePage, dumps
from scriptor.reflow.core import main


def _frag(text, x0, baseline, size=9.0):
    box = Box(x0, baseline - 7.0, x0 + 6 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


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


def test_a_reference_list_arrives_as_one_paragraph_per_entry(tmp_path):
    """The hanging indent of a bibliography must not break entries apart."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    # Enough entries for the hanging indent to look like the page's paragraph
    # indent: without the reference logic every continuation line is cut off as a
    # paragraph of its own, and no citation survives in one piece.
    lines = [
        ("Der letzte Satz des laufenden Textes steht hier und endet.", 30.0, 40.0, 9.0),
        ("References", 30.0, 60.0, 11.0),
        ("[1] Akari Asai and Hannaneh Hajishirzi. 2024. Self-RAG: Learning", 30.0, 75.0, 7.0),
        ("to Retrieve, Generate and Critique. In Proceedings of ICLR.", 40.0, 85.0, 7.0),
        ("[2] Mark Chen and Jerry Tworek. 2021. Evaluating Large Language", 30.0, 95.0, 7.0),
        ("Models Trained on Code. arXiv preprint (2021).", 40.0, 105.0, 7.0),
        ("[3] Gordon V. Cormack and Charles L. A. Clarke. 2009. Reciprocal", 30.0, 115.0, 7.0),
        ("Rank Fusion Outperforms Condorcet. In Proceedings of SIGIR.", 40.0, 125.0, 7.0),
        ("[4] Thibault Formal and Benjamin Piwowarski. 2021. SPLADE v2:", 30.0, 135.0, 7.0),
        ("Sparse Lexical and Expansion Model. arXiv preprint (2021).", 40.0, 145.0, 7.0),
        ("[5] Yunfan Gao and Yun Xiong. 2024. Retrieval-Augmented Genera-", 30.0, 155.0, 7.0),
        ("tion for Large Language Models: A Survey. arXiv preprint (2024).", 40.0, 165.0, 7.0),
    ]
    page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf",
                      lines=[_frag(*f) for f in lines])
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "paper.txt"
    main(str(pages_dir), str(out))

    text = out.read_text(encoding="utf-8")
    assert (
        "[1] Akari Asai and Hannaneh Hajishirzi. 2024. Self-RAG: Learning to Retrieve, "
        "Generate and Critique. In Proceedings of ICLR." in text
    )
    assert (
        "[2] Mark Chen and Jerry Tworek. 2021. Evaluating Large Language Models "
        "Trained on Code. arXiv preprint (2021)." in text
    )
    # The line-break hyphen inside an entry is resolved like anywhere else.
    assert "Retrieval-Augmented Generation for Large Language Models" in text


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


def _bold(text, x0, baseline, size=9.0):
    box = Box(x0, baseline - 7.0, x0 + 6 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size, bold=True)], box=box,
                baseline=baseline)


def test_a_heading_ends_the_paragraph_it_follows(tmp_path):
    """A column ends mid-sentence often enough that the running paragraph is
    still open when the next heading arrives. The typesetter set it apart, so it
    closes what is open instead of being swallowed by it."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page = SourcePage(
        index=1, width=300.0, height=400.0, source="pymupdf",
        lines=[
            _frag("Ein Absatz aus mehreren Zeilen, damit die Seite als", 30.0, 20.0),
            _frag("laufender Text erkannt wird und nicht als Rohseite,", 30.0, 32.0),
            _frag("denn nur dort werden Absaetze ueberhaupt gebildet und", 30.0, 44.0),
            _frag("Der vorige Absatz laeuft ohne Satzzeichen weiter und", 30.0, 56.0),
            _bold("3 Methodology", 30.0, 76.0),
            _frag("Der neue Abschnitt beginnt hier mit eigenem Text und", 30.0, 96.0),
            _frag("laeuft ueber mehrere Zeilen weiter bis zum Ende hier.", 30.0, 108.0),
        ],
    )
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "paper.md"
    main(str(pages_dir), str(out))

    text = out.read_text(encoding="utf-8")
    assert "\n# 3 Methodology\n" in text
    assert "weiter und 3 Methodology" not in text


def test_a_heading_broken_over_two_lines_stays_one_heading(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page = SourcePage(
        index=1, width=300.0, height=400.0, source="pymupdf",
        lines=[
            _frag("Ein Absatz aus mehreren Zeilen, damit die Seite als", 30.0, 20.0),
            _frag("laufender Text erkannt wird und nicht als Rohseite.", 30.0, 32.0),
            _bold("4.1 Experiment 1: Retrieval Mode, Harness, and", 30.0, 52.0),
            _bold("Tool Calling Method", 30.0, 64.0),
            _frag("Wir isolieren zunaechst den Einfluss des Modus und", 30.0, 84.0),
            _frag("berichten die Ergebnisse in der folgenden Tabelle.", 30.0, 96.0),
        ],
    )
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "paper.md"
    main(str(pages_dir), str(out))

    text = out.read_text(encoding="utf-8")
    assert "## 4.1 Experiment 1: Retrieval Mode, Harness, and Tool Calling Method" in text


def test_a_bullet_opens_a_paragraph(tmp_path):
    """Sen et al. p.1: "The paper contributes in three ways: • Retrieval, harness,
    and presentation. …" — the first item of a list runs on from the sentence that
    introduces it, because the bullet sits on the same printed line as its text."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    _write(pages_dir, 1, [
        ("Der einleitende Satz nennt drei Beitraege der Arbeit:", 30.0, 40.0),
        ("• Erstens die Evidenz zur Wahl des Verfahrens und", 30.0, 52.0),
        ("seiner Wirkung im laufenden Betrieb der Agenten.", 36.0, 64.0),
        ("• Zweitens die Charakterisierung des Verhaltens bei", 30.0, 76.0),
        ("wachsendem Anteil irrelevanter Nachbarschaft.", 36.0, 88.0),
    ])

    out = tmp_path / "paper.md"
    main(str(pages_dir), str(out))

    text = out.read_text(encoding="utf-8")
    assert "drei Beitraege der Arbeit: • Erstens" not in text
    assert "\n• Erstens die Evidenz" in text
    assert "\n• Zweitens die Charakterisierung" in text
