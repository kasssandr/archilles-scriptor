from docx_helpers import doc_xml, para_xml, run_xml, minimal_docx_bytes
from scriptor.docx.document import (
    Document, mark_attached, move_after, append_flag, highlight_run, qn,
)


def test_paragraphs_and_text():
    doc = Document.from_document_xml(doc_xml(
        para_xml(text="First paragraph."),
        para_xml(text="Second paragraph."),
    ))
    paras = doc.paragraphs
    assert [p.text for p in paras] == ["First paragraph.", "Second paragraph."]


def test_superscript_digit_is_detected_plain_paren_is_not():
    doc = Document.from_document_xml(doc_xml(
        para_xml(
            run_xml("owning Christian slaves."),
            run_xml("8", superscript=True),
            run_xml(" Following the rule, see also "),
            run_xml("(9)"),  # normale Klammerzahl, NICHT superscript
        ),
    ))
    refs = doc.paragraphs[0].superscript_digits()
    assert [r.number for r in refs] == [8]


def test_style_name_reads_pstyle():
    doc = Document.from_document_xml(doc_xml(
        '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
        '<w:r><w:t>x</w:t></w:r></w:p>',
        para_xml(text="no style"),
    ))
    assert doc.paragraphs[0].style_name == "Normal"
    assert doc.paragraphs[1].style_name is None


def test_load_from_minimal_docx(tmp_path):
    p = tmp_path / "in.docx"
    p.write_bytes(minimal_docx_bytes(doc_xml(para_xml(text="Hello"))))
    doc = Document.load(p)
    assert doc.paragraphs[0].text == "Hello"


def test_mark_attached_sets_style_and_indent():
    doc = Document.from_document_xml(doc_xml(para_xml(text="8.) Source.")))
    para = doc.paragraphs[0]
    mark_attached(para, "FootnoteAttached")
    assert para.style_name == "FootnoteAttached"
    ppr = para.elem.find(qn("pPr"))
    assert ppr.find(qn("ind")).get(qn("left")) == "720"
    # pStyle muss vor ind stehen (Schema-Reihenfolge)
    kids = [k.tag for k in ppr]
    assert kids.index(qn("pStyle")) < kids.index(qn("ind"))


def test_move_after_reorders_and_preserves_order():
    doc = Document.from_document_xml(doc_xml(
        para_xml(text="REF"),
        para_xml(text="OTHER"),
        para_xml(text="DEF1"),
        para_xml(text="DEF2"),
    ))
    ref, _other, def1, def2 = doc.paragraphs
    move_after(def1, ref)
    move_after(def2, def1)  # Anker fortschreiben -> Reihenfolge bleibt
    assert [p.text for p in doc.paragraphs] == ["REF", "DEF1", "DEF2", "OTHER"]


def test_append_flag_adds_highlighted_run():
    doc = Document.from_document_xml(doc_xml(para_xml(text="8.) Source.")))
    para = doc.paragraphs[0]
    append_flag(para, "[?FN:8: keine Referenz]")
    assert "[?FN:8: keine Referenz]" in para.text
    runs = list(para.elem.iter(qn("r")))
    last_rpr = runs[-1].find(qn("rPr"))
    assert last_rpr.find(qn("highlight")).get(qn("val")) == "yellow"


def test_highlight_run_sets_yellow():
    doc = Document.from_document_xml(doc_xml(
        para_xml(run_xml("x"), run_xml("8", superscript=True)),
    ))
    run = doc.paragraphs[0].superscript_digits()[0]
    highlight_run(run)
    rpr = run.elem.find(qn("rPr"))
    assert rpr.find(qn("highlight")).get(qn("val")) == "yellow"


def test_save_roundtrip_keeps_other_zip_entries(tmp_path):
    src = tmp_path / "in.docx"
    src.write_bytes(minimal_docx_bytes(doc_xml(para_xml(text="Hi"))))
    doc = Document.load(src)
    out = tmp_path / "out.docx"
    doc.save(out)
    import zipfile
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names
    assert Document.load(out).paragraphs[0].text == "Hi"
