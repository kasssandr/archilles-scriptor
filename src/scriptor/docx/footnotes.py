"""Binding logic on top of the document.py abstraction: detect footnote
references and loose ``N.)`` definitions, pair them up by position, attach
them, and flag anything uncertain. Conservative: only unambiguous pairs are
acted on."""
from __future__ import annotations

import re
from dataclasses import dataclass

from scriptor.docx.document import (
    Document, Paragraph, Run,
    mark_attached, move_after, append_flag, highlight_run,
)

# Loose footnote definition: "N.) Text" or "N) Text" (closing parenthesis
# required; "N." without a parenthesis are TOC/chapter lines and are excluded).
FN_DEF_RE = re.compile(r"^(\d{1,3})\.?\)\s")
# Left indent (twips) of attached definitions; also doubles as an idempotency marker.
ATTACHED_INDENT = 720


def _snippet(text: str, length: int = 70) -> str:
    """Short start-of-passage text findable via LibreOffice/Word search — the
    paragraph number itself isn't visible there, so this text snippet serves
    as a jump target. An already-set ``[?FN:…]`` flag is hidden (idempotency:
    the snippet stays stable across multiple runs)."""
    text = " ".join(text.split("[?FN:")[0].split())
    if len(text) <= length:
        return text
    cut = text[:length].rstrip()
    sp = cut.rfind(" ")
    if sp > length // 2:
        cut = cut[:sp]
    return cut + " …"


@dataclass
class Ref:
    para_index: int
    number: int
    run: Run


@dataclass
class Def:
    para_index: int
    number: int
    para: Paragraph
    is_attached: bool


def collect(doc: Document) -> tuple[list[Ref], list[Def]]:
    """Collects all superscript-digit references and all ``N.)`` definitions in
    document order. Definitions already attached (ATTACHED_STYLE) are carried
    along with ``is_attached=True`` — they still consume their reference later
    on, but are not moved again (idempotency)."""
    refs: list[Ref] = []
    defs: list[Def] = []
    for i, para in enumerate(doc.paragraphs):
        for run in para.superscript_digits():
            refs.append(Ref(i, run.number, run))
        m = FN_DEF_RE.match(para.text)
        if m:
            defs.append(Def(i, int(m.group(1)), para, para.left_indent == ATTACHED_INDENT))
    return refs, defs


def assign(
    refs: list[Ref], defs: list[Def]
) -> tuple[list[tuple[Ref, Def]], list[Def], list[Ref]]:
    """Assigns each definition to the last preceding, still-free reference with
    the same number. Returns (pairs, orphan_defs, orphan_refs); ``pairs``
    contains only definitions not yet attached (still to be moved)."""
    pairs: list[tuple[Ref, Def]] = []
    orphan_defs: list[Def] = []
    claimed: set[int] = set()  # id(ref) already claimed

    for d in sorted(defs, key=lambda d: d.para_index):
        cands = [
            r for r in refs
            if r.number == d.number
            and r.para_index <= d.para_index
            and id(r) not in claimed
        ]
        if not cands:
            orphan_defs.append(d)
            continue
        ref = max(cands, key=lambda r: r.para_index)
        claimed.add(id(ref))
        if not d.is_attached:
            pairs.append((ref, d))

    orphan_refs = [r for r in refs if id(r) not in claimed]
    return pairs, orphan_defs, orphan_refs


@dataclass
class BindReport:
    # Each is (para_index, number, snippet) — para_index first, so the lists
    # sort by running paragraph number (not by the footnote number, which
    # restarts at 1 per chapter); snippet is a searchable text example of
    # the passage.
    attached: list[tuple[int, int, str]]      # ref_para_index
    orphan_defs: list[tuple[int, int, str]]   # def_para_index
    orphan_refs: list[tuple[int, int, str]]   # ref_para_index


def bind(doc: Document) -> BindReport:
    """Moves unambiguously assignable definitions to an indented paragraph
    right after their reference; flags anything uncertain in yellow. In-place,
    idempotent."""
    refs, defs = collect(doc)
    pairs, orphan_defs, orphan_refs = assign(refs, defs)

    # The paragraphs list is static (elements); indices stay valid for the report.
    paras = doc.paragraphs

    # Attach: for each reference paragraph, the assigned defs in reference order.
    attached: list[tuple[int, int, str]] = []
    pairs_sorted = sorted(pairs, key=lambda rd: (rd[0].para_index, rd[1].para_index))
    anchor_by_ref: dict[int, Paragraph] = {}
    for ref, d in pairs_sorted:
        anchor = anchor_by_ref.get(ref.para_index, paras[ref.para_index])
        move_after(d.para, anchor)
        mark_attached(d.para)
        anchor_by_ref[ref.para_index] = d.para  # next def of this ref goes after it
        # Snippet from the reference paragraph (that's where the superscript
        # digit sits; the definition now hangs directly beneath it).
        attached.append((ref.para_index, d.number, _snippet(paras[ref.para_index].text)))

    # Capture the snippet BEFORE flagging, so the flag doesn't slip into it.
    orphan_def_entries: list[tuple[int, int, str]] = []
    for d in orphan_defs:
        orphan_def_entries.append((d.para_index, d.number, _snippet(d.para.text)))
        append_flag(d.para, f"[?FN:{d.number}: keine Referenz gefunden]")

    orphan_ref_entries: list[tuple[int, int, str]] = []
    for r in orphan_refs:
        orphan_ref_entries.append((r.para_index, r.number, _snippet(paras[r.para_index].text)))
        highlight_run(r.run)
        append_flag(paras[r.para_index], f"[?FN:{r.number}: keine Definition]")

    return BindReport(
        attached=sorted(attached),
        orphan_defs=sorted(orphan_def_entries),
        orphan_refs=sorted(orphan_ref_entries),
    )
