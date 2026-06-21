"""DOCX-Mechanik über lxml auf ``word/document.xml``: lesen, mutieren,
ZIP zurückschreiben. Kennt keine Fußnoten-Logik."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


@dataclass
class Run:
    elem: etree._Element
    text: str

    @property
    def number(self) -> int:
        return int("".join(c for c in self.text if c.isdigit()))


class Paragraph:
    def __init__(self, elem: etree._Element) -> None:
        self.elem = elem

    @property
    def text(self) -> str:
        return "".join(t.text or "" for t in self.elem.iter(qn("t"))).strip()

    def superscript_digits(self) -> list[Run]:
        out: list[Run] = []
        for r in self.elem.iter(qn("r")):
            txt = "".join(t.text or "" for t in r.iter(qn("t")))
            if not any(c.isdigit() for c in txt):
                continue
            rpr = r.find(qn("rPr"))
            if rpr is None:
                continue
            va = rpr.find(qn("vertAlign"))
            if va is not None and va.get(qn("val")) == "superscript":
                out.append(Run(r, txt))
        return out

    @property
    def style_name(self) -> str | None:
        ppr = self.elem.find(qn("pPr"))
        if ppr is None:
            return None
        st = ppr.find(qn("pStyle"))
        return st.get(qn("val")) if st is not None else None

    @property
    def left_indent(self) -> int | None:
        """Linke Einrückung in Twips (``w:ind/@w:left``) oder None."""
        ppr = self.elem.find(qn("pPr"))
        if ppr is None:
            return None
        ind = ppr.find(qn("ind"))
        if ind is None:
            return None
        val = ind.get(qn("left"))
        if val is None or not val.lstrip("-").isdigit():
            return None
        return int(val)


class Document:
    def __init__(self, root: etree._Element, others: dict[str, bytes] | None = None) -> None:
        self._root = root
        self._others = others or {}
        self._body = root.find(f".//{qn('body')}")
        if self._body is None:
            raise ValueError("w:body nicht gefunden")

    @classmethod
    def from_document_xml(cls, xml: str | bytes) -> "Document":
        if isinstance(xml, str):
            xml = xml.encode("utf-8")
        return cls(etree.fromstring(xml))

    @classmethod
    def load(cls, path: str | Path) -> "Document":
        with zipfile.ZipFile(path) as z:
            doc_xml = z.read("word/document.xml")
            others = {n: z.read(n) for n in z.namelist() if n != "word/document.xml"}
        return cls(etree.fromstring(doc_xml), others)

    def to_document_xml(self) -> bytes:
        return etree.tostring(
            self._root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [Paragraph(p) for p in self._body if p.tag == qn("p")]

    def save(self, path: str | Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", self.to_document_xml())
            for name, data in self._others.items():
                z.writestr(name, data)


def _get_or_make_ppr(p: etree._Element) -> etree._Element:
    ppr = p.find(qn("pPr"))
    if ppr is None:
        ppr = etree.Element(qn("pPr"))
        p.insert(0, ppr)  # pPr muss erstes Kind von w:p sein
    return ppr


# CT_PPr-Schema: Kind-Elemente, die NACH <w:ind> stehen müssen. <w:ind> wird
# unmittelbar vor dem ersten solchen Element eingefügt — sonst (z. B. ind nach
# rPr) verwirft Word das Dokument als beschädigt und repariert es mit Datenverlust.
_PPR_AFTER_IND = {
    "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl",
    "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
}


def mark_attached(para: Paragraph, indent_twips: int = 720) -> None:
    """Rückt den Absatz links ein — kennzeichnet eine angehängte Definition und
    dient zugleich als Idempotenz-Marker. Fügt ``w:ind`` schema-konform ein;
    pStyle und Runs bleiben unangetastet. Idempotent (höchstens ein ``w:ind``)."""
    ppr = _get_or_make_ppr(para.elem)
    ind = ppr.find(qn("ind"))
    if ind is None:
        ind = etree.Element(qn("ind"))
        anchor = next(
            (c for c in ppr if c.tag.rsplit("}", 1)[-1] in _PPR_AFTER_IND), None
        )
        if anchor is not None:
            anchor.addprevious(ind)
        else:
            ppr.append(ind)
    ind.set(qn("left"), str(indent_twips))


def move_after(moved: Paragraph, anchor: Paragraph) -> None:
    """Löst ``moved`` aus seiner Position und hängt es unmittelbar hinter
    ``anchor`` ein."""
    p = moved.elem
    parent = p.getparent()
    if parent is not None:
        parent.remove(p)
    anchor.elem.addnext(p)


def append_flag(para: Paragraph, flag_text: str) -> None:
    """Hängt einen gelb hervorgehobenen Run mit ``flag_text`` ans Absatzende.
    Idempotent: tut nichts, wenn der Absatz bereits ein ``[?FN:``-Flag trägt."""
    if "[?FN:" in para.text:
        return
    r = etree.SubElement(para.elem, qn("r"))
    rpr = etree.SubElement(r, qn("rPr"))
    etree.SubElement(rpr, qn("highlight")).set(qn("val"), "yellow")
    t = etree.SubElement(r, qn("t"))
    t.set(_XML_SPACE, "preserve")
    t.text = " " + flag_text


def highlight_run(run: Run) -> None:
    """Setzt gelbe Hervorhebung auf einen bestehenden Run (idempotent)."""
    rpr = run.elem.find(qn("rPr"))
    if rpr is None:
        rpr = etree.Element(qn("rPr"))
        run.elem.insert(0, rpr)
    hl = rpr.find(qn("highlight"))
    if hl is None:
        hl = etree.SubElement(rpr, qn("highlight"))
    hl.set(qn("val"), "yellow")
