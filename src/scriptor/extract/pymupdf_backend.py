"""PDF extraction via PyMuPDF's own text dictionary.

Writes one JSON file per page into ``out_dir`` with zero-padded filenames
(``00000001.json`` …) so the reflow stage can ingest them in order.

This backend reads the text layer a PDF already carries. It does not OCR. That is
not a limitation, it is the contract: which engine turns pixels into text is the
caller's decision (``extract/ocr_backend.py``). Two real books show why a library
that decides for itself is dangerous. Zuckerman's FineReader layer is rendered
*visibly*, so ``pymupdf4llm``'s default re-OCRed the page image and appended the
result -- every paragraph, footnote and marker twice. Susa and Thil-Lorrain carry
an *invisible* OCR layer, which the same default deletes and replaces, in the
default language, over a French text.

We read ``page.get_text("rawdict")``: blocks, lines, spans, each with ``bbox``,
``size``, ``font``, ``flags``, ``origin`` and its glyphs. Lines arrive in content-stream order
and are **not** sorted here -- reading order across columns is a judgement, and
judgements belong in scriptor code (``reflow/textlines.py``).
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pymupdf

from scriptor.page import RAISED, Box, Glyph, Line, Link, SourcePage, Span, dumps

_BOLD = 16      # span["flags"] bit 4
_ITALIC = 2     # span["flags"] bit 1


def _box(raw) -> Box:
    return Box(*(round(float(v), 2) for v in raw))


def _span_text(raw: dict) -> str:
    """``dict`` spans carry ``text``; ``rawdict`` spans carry ``chars`` instead."""
    if "text" in raw:
        return raw["text"]
    return "".join(c["c"] for c in raw.get("chars", ()))


def _span(raw: dict) -> Span:
    return Span(
        text=_span_text(raw),
        box=_box(raw["bbox"]),
        size=round(float(raw["size"]), 2),
        bold=bool(raw["flags"] & _BOLD),
        italic=bool(raw["flags"] & _ITALIC),
    )


# Text in white ink, set on the bare page, is in the file and not on the page.
# Word leaves it there: Fried's Donation of Constantine carries its footnote
# separator as a white "h" above every apparatus (118 times), and its contents
# page sets a white "1" before each printed page number, so the text layer reads
# "135" where the page shows 35. The Russian volumes of the corpus hide truncated
# chapter titles so; Josephus and Jesus a 1-pt producer stamp. Rendered, none of
# them leaves a dark pixel (measured 2026-11-04 over 25 volumes). White ink over
# an image or a filled shape is printed and stays: a cover title set light on
# dark is text the page shows.
_WHITE = 0xFFFFFF


def _ground(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """What white ink could be printed on: images and shapes filled in a colour."""
    under = [pymupdf.Rect(info["bbox"]) for info in page.get_image_info()]
    under += [d["rect"] for d in page.get_drawings()
              if d.get("fill") is not None and tuple(d["fill"]) != (1.0, 1.0, 1.0)]
    return under


def _invisible(raw: dict, ground: list[pymupdf.Rect]) -> bool:
    if raw.get("color") != _WHITE:
        return False
    x0, y0, x1, y1 = raw["bbox"]
    centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
    return not any(centre in rect for rect in ground)


# A word space the file never wrote. Some typesetters set the space after a full
# stop, and after a raised note number, as a bare move of the pen: Ando's Matter
# of the Gods (UC Press 2008) moves 1.56 pt and draws no space glyph, so MuPDF
# reads "halves.The three" and "myths.3Regardless" -- 120 sentences and 40 note
# numbers glued to the next word, and a marker glued to a word is no marker. The
# same move stands between the letters of a letter-spaced running head and the
# digits of a folio, so a gap alone is no space: it is one after a sentence's
# punctuation, or after a number set smaller than the text it is followed by.
#
# Measured over the corpus (2026-11-08, ~400 PDFs) the move is no space either
# inside an abbreviation ("A.D.", "a.a.O.", "D.C." -- one letter before the
# stop) or a siglum (a capital before it: "BL.Add."), before right-to-left script (Arabic and Syriac set the stop before the
# word), after a closing bracket in letter-spaced type, or after a subscript
# index in a formula, or where the next word does not begin as a sentence does
# (a capital and then a small letter or a space: "Ph.D.", "www.uni-hamburg.de"
# and an OCR layer's "CHAI.D/" do not): those stay as the file wrote them.
_GAP_EM = 0.05
_STOPS = ".?!;:"
_QUOTES = "”’"
_OPENS = "“‘"


def _ltr_letter(ch: str) -> bool:
    return ch.isalpha() and unicodedata.bidirectional(ch) == "L"


def _ends_sentence(before: str) -> bool:
    """Whether the drawn text ``before`` the gap closes a sentence."""
    if before[-1:] in _QUOTES:
        before = before[:-1]
        if before[-1:] in _QUOTES:
            before = before[:-1]
        return before[-1:] in _STOPS + ","
    if before[-1:] not in _STOPS:
        return False
    word = before[:-1]
    # One letter before the stop is an initial or an abbreviation's part; a
    # capital before it a siglum ("BL.Add.12150", "PubL.Syri") or OCR debris.
    return len(word) >= 2 and word[-1].islower() and word[-2].isalpha()


def _opens_sentence(ch: str, after: str) -> bool:
    """Whether a word beginning ``ch`` and going on ``after`` begins a sentence."""
    if ch in _OPENS:
        return True
    return _ltr_letter(ch) and ch.isupper() and (after == "" or after.isspace() or after.islower())


def _open_gaps(raw_spans: list[dict]) -> list[dict]:
    """``rawdict`` spans with their text, a space put where the pen moved over one."""
    flat = [c["c"] for s in raw_spans for c in s.get("chars", ())]
    at = 0                      # index of the current char in ``flat``
    out: list[dict] = []
    prev = None                 # (char, span) last drawn
    drawn = ""                  # the line's text so far
    for s in raw_spans:
        text = []
        for c in s.get("chars", ()):
            ch = c["c"]
            if prev is not None and not ch.isspace() and not prev[0]["c"].isspace():
                pc, ps = prev
                gap = c["bbox"][0] - pc["bbox"][2]
                if gap >= _GAP_EM * max(ps["size"], s["size"]) and (
                        _ltr_letter(ch) or ch in _OPENS):
                    raised = (pc["c"].isdigit() and ps is not s
                              and ps["size"] < 0.85 * s["size"]
                              and ps["origin"][1] < s["origin"][1] - 0.5)
                    after = flat[at + 1] if at + 1 < len(flat) else ""
                    if raised or (_ends_sentence(drawn) and _opens_sentence(ch, after)):
                        text.append(" ")
                        drawn += " "
            text.append(ch)
            drawn += ch
            prev = (c, s)
            at += 1
        out.append({**s, "text": "".join(text)})
    return out


def _glyphs(raw_spans: list[dict]) -> list[Glyph]:
    return [
        Glyph(char=c["c"], box=_box(c["bbox"]))
        for span in raw_spans
        for c in span.get("chars", ())
    ]


def _links(page: pymupdf.Page) -> list[Link]:
    """The links that point somewhere inside this document.

    A URI is dropped: it says nothing about this volume's pagination. What
    remains has to name a page, and pymupdf reports that in ``page`` -- as an
    int for a plain GoTo, and as a string for a named destination it resolved
    (Libros' contents links come through that way). A name it could *not*
    resolve arrives as a string that is not a number, and is dropped: an
    unresolved name is not a page reference.

    Reported 1-based, like ``SourcePage.index``, because everything downstream
    counts pages that way. pymupdf counts from zero.
    """
    out: list[Link] = []
    for raw in page.get_links():
        if raw.get("kind") not in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
            continue
        target = raw.get("page")
        if isinstance(target, str):
            target = int(target) - 1 if target.strip().isdigit() else None
        if target is None or target < 0:
            continue
        rect = raw.get("from")
        if rect is None:
            continue
        out.append(Link(box=_box(rect), target=target + 1))
    return out


def read_page(page: pymupdf.Page, index: int, *, glyphs: bool = False,
              unseen: list[str] | None = None) -> SourcePage:
    """One page of the model. ``glyphs`` costs roughly twenty times the size.

    Text the page does not show (white ink on the bare page) is not read; what
    it said is appended to ``unseen``, so the caller can report it.
    """
    # Always the glyphs: a space the file only moved over shows in their boxes.
    raw = page.get_text("rawdict")
    white = any(s.get("color") == _WHITE
                for block in raw["blocks"] if block.get("type") == 0
                for raw_line in block["lines"] for s in raw_line["spans"])
    ground = _ground(page) if white else []
    lines: list[Line] = []
    for block in raw["blocks"]:
        if block.get("type") != 0:      # 0 = text, 1 = image
            continue
        for raw_line in block["lines"]:
            kept = []
            hidden = False
            gap = False
            for s in _open_gaps(raw_line["spans"]):
                if not _span_text(s):
                    continue
                if white and _invisible(s, ground):
                    hidden = True
                    gap = bool(kept)
                    if unseen is not None and _span_text(s).strip():
                        unseen.append(_span_text(s).strip())
                    continue
                if gap and not (_span_text(kept[-1])[-1:].isspace()
                                or _span_text(s)[:1].isspace()):
                    # The unseen text held a place on the page, and the page
                    # shows it as space: Fried's contents read "Introduction
                    # ......1" once the white "11" between leader and page
                    # number was gone, and no page number was found.
                    s = {**s, "text": " " + _span_text(s)}
                gap = False
                kept.append(s)
            spans = [_span(s) for s in kept]
            if not spans:
                continue
            box = _box(raw_line["bbox"])
            if hidden:
                # What is left of the line is what the page shows: the run of
                # blanks the separator stood behind is no line, and the box
                # shrinks to the ink that remains.
                if not "".join(sp.text for sp in spans).strip():
                    continue
                box = Box(min(sp.box.x0 for sp in spans), min(sp.box.y0 for sp in spans),
                          max(sp.box.x1 for sp in spans), max(sp.box.y1 for sp in spans))
            # The baseline of the first span. Within a line all spans share it,
            # and it is what reflow/textlines.py clusters on -- the box top moves
            # with the ascenders of the words that happen to stand in the line.
            baseline = round(float(raw_line["spans"][0]["origin"][1]), 2)
            lines.append(
                Line(
                    spans=spans,
                    box=box,
                    baseline=baseline,
                    glyphs=_glyphs(kept) if glyphs else None,
                )
            )
    # The catalogue's printed label for this page (PDF PageLabels). An empty
    # string means the PDF declares none — omitted then, never invented.
    label = page.get_label()
    return SourcePage(
        index=index,
        lines=lines,
        width=round(page.rect.width, 2),
        height=round(page.rect.height, 2),
        source="pymupdf",
        label=label or None,
        links=_links(page),
    )


def extract(
    pdf_path: str | Path,
    out_dir: str | Path,
    *,
    emit_txt: bool = False,
    glyphs: bool = False,
) -> list[Path]:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    blank = 0
    unseen: list[str] = []
    with pymupdf.open(pdf_path) as doc:
        # The catalogue's outline: chapter titles with their physical start
        # page. A measured fact, written as a sidecar; whether to believe it
        # is reflow's decision (reflow/outline.py: credibility + per-page
        # confirmation).
        from scriptor.reflow.outline import OutlineEntry, save_outline
        save_outline(
            [
                OutlineEntry(level=level, title=title.strip(), page=page)
                for level, title, page in doc.get_toc()
                if page >= 1
            ],
            out_dir,
        )
        for index, page in enumerate(doc, start=1):
            source_page = read_page(page, index, glyphs=glyphs, unseen=unseen)
            path = out_dir / f"{index:08d}.json"
            path.write_text(dumps(source_page), encoding="utf-8")
            written.append(path)
            if not source_page.lines:
                blank += 1
            if emit_txt:
                # A derived channel for human eyes, in its own directory: written
                # beside the JSON it would collide with it, and load_pages refuses
                # to choose between two files for one page.
                txt_dir = out_dir / "txt"
                txt_dir.mkdir(exist_ok=True)
                (txt_dir / f"{index:08d}.txt").write_text(
                    source_page.text.replace(RAISED, "") + "\n", encoding="utf-8"
                )

    if unseen:
        sample = ", ".join(repr(t) for t in dict.fromkeys(unseen))
        print(
            f"Text in white ink on the bare page, not read: {len(unseen)} spans "
            f"({sample[:120]})",
            file=sys.stderr,
        )
    # A page without a text layer is not an empty page -- it is a page this backend
    # cannot read. Say so, rather than handing the reflow stage a file that looks
    # like a plate or a blank leaf. Sigilla Veri: 606 of 606.
    if blank:
        print(
            f"{blank} of {len(written)} pages carry no text layer. "
            f"This backend does not OCR; a scan needs an OCR backend.",
            file=sys.stderr,
        )
    return written
