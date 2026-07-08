"""Builds WordprocessingML fragments and minimal DOCX bytes for tests.
Test texts must not contain raw XML special characters (& < >)."""
from __future__ import annotations

import io
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def run_xml(text: str, *, superscript: bool = False) -> str:
    rpr = '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr>' if superscript else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r>'


def para_xml(*runs: str, text: str | None = None) -> str:
    if text is not None:
        runs = (run_xml(text),)
    return f"<w:p>{''.join(runs)}</w:p>"


def doc_xml(*paras: str) -> str:
    return (
        f'<w:document xmlns:w="{W}"><w:body>{"".join(paras)}</w:body></w:document>'
    )


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)


def minimal_docx_bytes(document_xml: str | bytes) -> bytes:
    if isinstance(document_xml, str):
        document_xml = document_xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()
