from docx_helpers import doc_xml, para_xml, run_xml, minimal_docx_bytes
from scriptor.docx.document import Document


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
