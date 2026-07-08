from docx_helpers import doc_xml, para_xml, run_xml, minimal_docx_bytes
from scriptor.docx.document import Document
from scriptor import pipeline
from scriptor.cli import main as cli_main


def _make_docx(tmp_path, name="in.docx"):
    p = tmp_path / name
    p.write_bytes(minimal_docx_bytes(doc_xml(
        para_xml(run_xml("a"), run_xml("8", superscript=True)),
        para_xml(text="filler"),
        para_xml(text="8.) Source eight."),
        para_xml(run_xml("b"), run_xml("9", superscript=True)),  # orphan ref
    )))
    return p


def test_pipeline_bind_footnotes_writes_output_and_log(tmp_path):
    src = _make_docx(tmp_path)
    out = tmp_path / "out.docx"
    report = pipeline.bind_footnotes(src, out)
    assert out.exists()
    log = out.with_name(out.name + ".bind-log.txt")
    assert log.exists()
    assert report.attached == [(0, 8, "a8")]   # (para_index, number, snippet)
    assert [n for _, n, _ in report.orphan_refs] == [9]
    # Report sidecar: by paragraph number, with a searchable snippet
    log_text = log.read_text(encoding="utf-8")
    assert "Paragraph" in log_text and "»a8«" in log_text
    # Definition directly after the reference in the written DOCX
    texts = [p.text for p in Document.load(out).paragraphs]
    assert texts[1] == "8.) Source eight."
    # Original unchanged
    assert [p.text for p in Document.load(src).paragraphs][1] == "filler"


def test_cli_bind_footnotes(tmp_path, capsys):
    src = _make_docx(tmp_path)
    out = tmp_path / "out.docx"
    rc = cli_main(["bind-footnotes", str(src), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert out.with_name(out.name + ".bind-log.txt").exists()
