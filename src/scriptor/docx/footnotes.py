"""Binde-Logik über der document.py-Abstraktion: Fußnoten-Referenzen und
lose ``N.)``-Definitionen erkennen, positionsbasiert zuordnen, anhängen,
Unsicheres markieren. Konservativ: nur eindeutige Paare werden ausgeführt."""
from __future__ import annotations

import re
from dataclasses import dataclass

from scriptor.docx.document import (
    Document, Paragraph, Run,
    mark_attached, move_after, append_flag, highlight_run,
)

# Lose Fußnoten-Definition: "N.) Text" oder "N) Text" (schließende Klammer
# zwingend; "N." ohne Klammer sind TOC-/Kapitelzeilen und werden ausgeschlossen).
FN_DEF_RE = re.compile(r"^(\d{1,3})\.?\)\s")
# Linke Einrückung (Twips) angehängter Definitionen; zugleich Idempotenz-Marker.
ATTACHED_INDENT = 720


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
    """Sammelt alle Superscript-Ziffern-Referenzen und alle ``N.)``-Definitionen
    in Dokumentreihenfolge. Schon angehängte Definitionen (ATTACHED_STYLE) werden
    mit ``is_attached=True`` mitgeführt — sie verbrauchen später ihre Referenz,
    werden aber nicht erneut verschoben (Idempotenz)."""
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
    """Ordnet jede Definition der letzten vorausgehenden, noch freien Referenz
    gleicher Nummer zu. Gibt (pairs, orphan_defs, orphan_refs) zurück; ``pairs``
    enthält nur nicht angehängte Definitionen (zu verschieben)."""
    pairs: list[tuple[Ref, Def]] = []
    orphan_defs: list[Def] = []
    claimed: set[int] = set()  # id(ref) bereits vergeben

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
    attached: list[tuple[int, int]]      # (number, ref_para_index)
    orphan_defs: list[tuple[int, int]]   # (number, def_para_index)
    orphan_refs: list[tuple[int, int]]   # (number, ref_para_index)


def bind(doc: Document) -> BindReport:
    """Verschiebt eindeutig zuordenbare Definitionen als eingerückten Folgeabsatz
    hinter ihre Referenz; markiert Unsicheres gelb. In-place, idempotent."""
    refs, defs = collect(doc)
    pairs, orphan_defs, orphan_refs = assign(refs, defs)

    # paragraphs-Liste ist statisch (Elemente), Indizes bleiben für Report gültig.
    paras = doc.paragraphs

    # Anhängen: pro Referenz-Absatz die zugeordneten Defs in Referenz-Reihenfolge.
    attached: list[tuple[int, int]] = []
    pairs_sorted = sorted(pairs, key=lambda rd: (rd[0].para_index, rd[1].para_index))
    anchor_by_ref: dict[int, Paragraph] = {}
    for ref, d in pairs_sorted:
        anchor = anchor_by_ref.get(ref.para_index, paras[ref.para_index])
        move_after(d.para, anchor)
        mark_attached(d.para)
        anchor_by_ref[ref.para_index] = d.para  # nächste Def dieser Ref dahinter
        attached.append((d.number, ref.para_index))

    for d in orphan_defs:
        append_flag(d.para, f"[?FN:{d.number}: keine Referenz gefunden]")
    for r in orphan_refs:
        highlight_run(r.run)
        append_flag(paras[r.para_index], f"[?FN:{r.number}: keine Definition]")

    return BindReport(
        attached=sorted(attached),
        orphan_defs=sorted((d.number, d.para_index) for d in orphan_defs),
        orphan_refs=sorted((r.number, r.para_index) for r in orphan_refs),
    )
