"""Tests für die I/O-Anbindung des Übersetzungs-Profils (pipeline.translate_prep)."""

from scriptor import pipeline


def test_translate_prep_writes_deliverable_and_briefing(tmp_path):
    master = tmp_path / "book.md"
    master.write_text(
        'Body http://a.org\n[^3]: Vgl. „Titel“, Berlin. [?FN:4|A]\n',
        encoding="utf-8",
    )
    out = tmp_path / "book.translate.md"
    briefing = pipeline.translate_prep(master, out)

    deliverable = out.read_text(encoding="utf-8")
    assert "<dnt>http://a.org</dnt>" in deliverable
    assert "<dnt>„Titel“</dnt>" in deliverable
    assert "[?FN" not in deliverable
    assert briefing == tmp_path / "book.translate.briefing.txt"
    assert briefing.read_text(encoding="utf-8").strip()  # nicht leer
