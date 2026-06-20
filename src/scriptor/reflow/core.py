"""
PDF-Text-Reflow für gescannte Bücher.

Eingabe: ein Verzeichnis mit OCR-Textdateien (eine pro Seite, sortiert).
Ausgabe: eine zusammengeführte TXT-Datei mit:
  - rekonstruierten Absätzen
  - de-hyphenierten Wörtern
  - Fußnoten am Absatzende eingerückt
  - Seitenmarkern [S. NN] inline
  - Fußnoten-Markern [NN] im Fließtext
"""

from __future__ import annotations
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from scriptor.reflow.footnotes import (
    FOOTNOTE_RE,
    PLACED_MARKER_RE,
    SUPERSCRIPT_DIGITS,
    substitute_markers,
)

# --- Konfiguration ---
INDENT = "    "                # Einrückung der Fußnoten am Absatzende
PAGENUM_RE = re.compile(r"^\d{1,4}$")
# FOOTNOTE_RE, PLACED_MARKER_RE, SUPERSCRIPT_DIGITS und substitute_markers
# leben jetzt in footnotes.py (oben importiert).


@dataclass
class Page:
    num: int                              # Seitenzahl laut Datei
    body_lines: list[str]                 # rohe Body-Zeilen
    footnotes: dict[int, str] = field(default_factory=dict)  # nr → Text
    mode: str = "main"                    # frontmatter | toc | main | entries-versal | entries-cap


# ----------------------------------------------------------------------
# 1) Seite parsen: Body / Fußnoten / Seitenzahl trennen
# ----------------------------------------------------------------------

def parse_page(text: str) -> Page | None:
    """Eine Seitendatei zerlegen. Gibt None zurück, falls leer."""
    text = text.translate(SUPERSCRIPT_DIGITS)
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None

    # Seitenzahl: letzte Zeile, wenn sie reine Ziffern ist
    page_num = -1
    if PAGENUM_RE.match(lines[-1].strip()):
        page_num = int(lines[-1].strip())
        lines.pop()

    # Fußnoten-Block: ab erster Zeile, die mit "NN)" beginnt — sofern danach
    # nur noch Fußnoten/Fortsetzungen folgen.
    fn_start = None
    for i, ln in enumerate(lines):
        if FOOTNOTE_RE.match(ln):
            fn_start = i
            break

    body_lines: list[str] = []
    fn_lines: list[str] = []
    if fn_start is None:
        body_lines = lines
    else:
        body_lines = lines[:fn_start]
        fn_lines = lines[fn_start:]

    # Fußnoten zusammenbauen (mehrzeilige Noten zusammenfügen, dehyphenieren)
    footnotes: dict[int, str] = {}
    cur_num: int | None = None
    cur_buf: list[str] = []

    def flush():
        if cur_num is None:
            return
        joined = dehyphenate_join(cur_buf)
        footnotes[cur_num] = joined.strip()

    for ln in fn_lines:
        m = FOOTNOTE_RE.match(ln)
        if m:
            flush()
            cur_num = int(m.group(1))
            cur_buf = [m.group(2)]
        else:
            cur_buf.append(ln)
    flush()

    # Footnote-Marker im Body durch [NN] ersetzen (in-place auf body_lines)
    body_lines = substitute_markers(body_lines, footnotes)

    return Page(num=page_num, body_lines=body_lines, footnotes=footnotes)


# ----------------------------------------------------------------------
# 2) Hilfsfunktionen: De-Hyphenierung
# ----------------------------------------------------------------------

# Kurze deutsche Verbindungswörter, vor denen ein Bindestrich beibehalten
# wird (Kompositum mit ausgesetztem Grundwort, z. B. 'Einzel- und Gesamt…').
KEEP_HYPHEN_BEFORE = re.compile(
    r"^(und|oder|bis|sowie|wie|als|zur?|zum?|noch|aber)\b", re.IGNORECASE
)


def is_hard_hyphen(prev: str, next_line: str) -> bool:
    """True, wenn das '-' am Ende von prev ein echter Kompositum-Bindestrich ist
    (sollte erhalten bleiben), False für Trennstrich (sollte verschwinden)."""
    return bool(KEEP_HYPHEN_BEFORE.match(next_line.lstrip()))


def dehyphenate_join(lines: list[str]) -> str:
    """Zeilen verbinden; trennt 'wort-\\n' → 'wort'."""
    out = []
    for i, ln in enumerate(lines):
        if i == 0:
            out.append(ln)
            continue
        prev = out[-1]
        if (
            prev.endswith("-")
            and len(prev) >= 2
            and prev[-2].isalpha()
            and ln[:1].isalpha()
            and not is_hard_hyphen(prev, ln)
        ):
            out[-1] = prev[:-1] + ln.lstrip()
        else:
            out[-1] = prev + " " + ln.lstrip()
    return out[0] if out else ""


# ----------------------------------------------------------------------
# 3) Kalibrierung: Zeilenlängen-Schwellwert für Absatzenden bestimmen
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Region-/Modus-Erkennung
# ----------------------------------------------------------------------

# Heading-Muster, die einen Modus-Wechsel auslösen.
# Geprüft werden die ersten 10 nicht-leeren Body-Zeilen einer Seite.
HEADING_TRIGGERS = [
    (re.compile(r"^INHALTSVERZEICHNIS\s*$"), "toc"),
    # Literaturverzeichnis: Versal-Nachnamen am Zeilenanfang sind klare Marker
    (re.compile(r"^\d+\.\s+Literatur\s*$"), "entries-versal"),
    # Abkürzungen / Quellen / Register: OCR-Spaltenscan oft kaputt → raw belassen
    (re.compile(
        r"^\d+\.\s+(Abkürzungsverzeichnis|Quellen|Personenregister|Sachregister|Ortsregister)\s*$"
    ), "raw"),
]


def assign_modes(pages: list[Page]) -> None:
    """Setzt p.mode für jede Seite anhand erkannter Region-Übergänge.

    Startmodus = 'frontmatter'. Wechsel:
      - Heading-Trigger (erste Body-Zeile matcht ein Pattern) → entsprechender Modus
      - Im Modus 'frontmatter' oder 'toc': sobald eine Seite mit Buchnr 1 auftaucht
        und kein Heading-Trigger vorlag → 'main'
    """
    mode = "frontmatter"
    for p in pages:
        # OCR kann Spalten in falscher Reihenfolge ausgeben — Heading kann
        # einige Zeilen verschoben sein. Wir prüfen die ersten 10 nicht-leeren.
        candidates = [ln.strip() for ln in p.body_lines if ln.strip()][:10]
        triggered = False
        for line in candidates:
            for pat, new_mode in HEADING_TRIGGERS:
                if pat.match(line):
                    mode = new_mode
                    triggered = True
                    break
            if triggered:
                break
        if not triggered and mode in ("frontmatter", "toc") and p.num == 1:
            mode = "main"
        p.mode = mode


def calibrate_threshold(pages: list[Page], peak_fraction: float = 0.25) -> tuple[int, Counter[int]]:
    """
    Erfasst Längen aller Body-Zeilen, ermittelt die linke Flanke des
    Haupt-Peaks ('volle Fließtextzeilen') und liefert daraus den maximalen
    Wert, bei dem eine Zeile noch als 'verdächtig kurz' gilt.

    Verfahren:
      1. Modus der Zeilenlängen finden (= häufigste Länge, typische volle Breite)
      2. Vom Modus aus nach links laufen, bis count < peak_fraction × peak_count
      3. Diese Position ist die linke Flanke; threshold = Position − 1.

    Lange Tails (Indizes, Überschriften) und ein evtl. zweiter Peak in
    den Fußnoten beeinflussen das Ergebnis nicht.
    """
    lengths: Counter[int] = Counter()
    for p in pages:
        if not p.body_lines or p.mode != "main":
            continue
        # Letzte Zeile pro Seite ausschließen — fast immer kurz wegen Layout
        for ln in p.body_lines[:-1]:
            if ln.strip():
                lengths[len(ln)] += 1

    if not lengths:
        return 0, lengths

    mode_len, mode_count = lengths.most_common(1)[0]
    cutoff = mode_count * peak_fraction
    left_edge = mode_len
    for ln_len in range(mode_len, 0, -1):
        if lengths.get(ln_len, 0) < cutoff:
            left_edge = ln_len + 1
            break
    threshold = left_edge - 1
    return threshold, lengths


# ----------------------------------------------------------------------
# 4) Body verarbeiten: Absatz-Rekonstruktion + Seitenmarker einbauen
# ----------------------------------------------------------------------

SENT_END = re.compile(r"[.!?»“\"’']$")  # einfache Satzendekennung


# Numerierte Überschrift am Absatzanfang: "3.4. Probleme um Welf VI."
# Heading-Level = Anzahl Punkte in der Numerierung + 1.
HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,3})\.\s+[A-ZÄÖÜ]")
HEADING_MAX_LEN = 80


def heading_level(line: str) -> int:
    """0 wenn keine Überschrift, sonst Level 1-4."""
    if len(line) > HEADING_MAX_LEN:
        return 0
    m = HEADING_RE.match(line)
    if not m:
        return 0
    return m.group(1).count(".") + 1


def reconstruct_body(
    pages: list[Page],
    threshold: int,
    audit: dict[int, list[int]] | None = None,
) -> tuple[list[str], list[dict[int, str]], list[int]]:
    """
    Liefert eine Liste von Absatz-Strings (Body, mit [S.NN]-Markern und
    [NN]-Fußnotenmarkern), parallel dazu pro Absatz einen dict mit den
    zugehörigen Fußnoten-Texten und ein Heading-Level (0 = normaler Absatz).

    Fußnoten, deren Marker auf der Seite nicht gefunden wurden (OCR-Fehler
    am Marker, nicht an der Def), werden am Seitenende an den zugehörigen
    Absatz angehängt, damit sie nicht verloren gehen. Die betroffenen Seiten
    werden zusätzlich in `audit[page_num] = [nums…]` vermerkt.
    """
    if audit is None:
        audit = {}
    paragraphs: list[str] = []
    para_footnotes: list[dict[int, str]] = []
    para_levels: list[int] = []

    cur_chunks: list[str] = []                 # Wort-Blöcke des aktuellen Absatzes
    cur_fn: dict[int, str] = {}                # Fußnoten dieses Absatzes
    pending_hyphen = False                     # vorheriger Chunk endet auf Trenn-
    pending_page_marker: str | None = None     # noch nicht eingefügter [S. NN]

    def end_paragraph(level: int = 0):
        nonlocal cur_chunks, cur_fn, pending_hyphen, pending_page_marker
        text = "".join(cur_chunks).strip()
        text = re.sub(r"[ \t]+", " ", text)
        if text:
            paragraphs.append(text)
            para_footnotes.append(cur_fn)
            para_levels.append(level)
        cur_chunks = []
        cur_fn = {}
        pending_hyphen = False
        pending_page_marker = None

    def flush_page_marker():
        nonlocal pending_page_marker
        if pending_page_marker is None:
            return
        if cur_chunks:
            cur_chunks.append(" ")
        cur_chunks.append(pending_page_marker)
        pending_page_marker = None

    def append_word_segment(seg: str):
        """Anhängen mit korrekter Behandlung von Trenn-Bindestrich und
        eines evtl. ausstehenden Seitenmarkers."""
        nonlocal pending_hyphen
        if not seg:
            return
        if pending_hyphen:
            cur_chunks.append(seg)            # ohne Leerzeichen, vervollständigt das Wort
            pending_hyphen = False
            flush_page_marker()               # Marker erst nach dem Wort einfügen
        else:
            flush_page_marker()
            if cur_chunks:
                cur_chunks.append(" ")
            cur_chunks.append(seg)

    for p in pages:
        if not p.body_lines or p.mode != "main":
            continue

        # Seitenmarker vormerken; einfügen nach evtl. offenem Wort
        if p.num >= 0:
            pending_page_marker = f"[S. {p.num}]"

        seen_this_page: set[int] = set()
        paragraphs_before_page = len(paragraphs)

        n = len(p.body_lines)
        for i, ln in enumerate(p.body_lines):
            stripped = ln.rstrip()
            if not stripped.strip():
                # Leerzeile mitten im Body → Absatzende
                end_paragraph()
                continue

            # Numerierte Überschrift am Absatzanfang (nur wenn noch kein
            # offenes Wort und kein laufender Absatz) → eigener Block.
            # Ein ausstehender Seitenmarker wird NICHT in das Heading gezogen,
            # sondern bleibt für den nachfolgenden Absatz vorgemerkt.
            if not cur_chunks and not pending_hyphen:
                lvl = heading_level(stripped)
                if lvl > 0:
                    saved_marker = pending_page_marker
                    pending_page_marker = None
                    cur_chunks.append(stripped)
                    end_paragraph(level=lvl)
                    pending_page_marker = saved_marker
                    continue

            # Trenn-Bindestrich am Ende? (nur wenn nächste Zeile NICHT mit
            # 'und/oder/...' beginnt — sonst ist es ein Kompositum-Strich)
            ends_hyphen = (
                len(stripped) >= 2 and stripped.endswith("-")
                and stripped[-2].isalpha()
            )
            if ends_hyphen and i + 1 < n:
                if is_hard_hyphen(stripped, p.body_lines[i + 1]):
                    ends_hyphen = False
            content = stripped[:-1] if ends_hyphen else stripped

            # Bereits platzierte [NN]-Marker registrieren, damit sie ans
            # Absatzende wandern.
            for m in PLACED_MARKER_RE.finditer(content):
                num = int(m.group(1))
                if num in p.footnotes:
                    cur_fn[num] = p.footnotes[num]
                    seen_this_page.add(num)

            append_word_segment(content)

            if ends_hyphen:
                pending_hyphen = True
            else:
                pending_hyphen = False
                # Absatzende-Heuristik: kurze Zeile + Satzendezeichen.
                # Auch die letzte Zeile einer Seite darf Paragraphende sein —
                # wenn sie wirklich ein Absatz war, beendet das den Absatz hier;
                # falls nicht, läuft der nächste Absatz auf der Folgeseite einfach
                # weiter (das passiert in der Praxis seltener als echte Absatzenden
                # am Seitenfuß).
                visible_len = len(stripped)
                if visible_len <= threshold and SENT_END.search(stripped):
                    end_paragraph()

        # Seitenende: nicht verankerte Fußnoten dieser Seite retten.
        # Sie landen im zuletzt berührten Absatz (offen oder zuletzt
        # geschlossen während dieser Seite). Der Renderer hängt sie als
        # hanging reference an — so gehen sie nicht verloren.
        unclaimed = sorted(set(p.footnotes) - seen_this_page)
        if unclaimed and p.num >= 0:
            audit[p.num] = unclaimed
            if cur_chunks:
                target = cur_fn
            elif len(paragraphs) > paragraphs_before_page:
                target = para_footnotes[-1]
            else:
                # Seite enthält nur Fußnoten-Defs ohne eigenen Body
                # (oder Body spannt nur einen bereits abgeschlossenen
                # Absatz der Vorseite an) — an den nächsten Absatz hängen.
                target = cur_fn
            for num in unclaimed:
                target[num] = p.footnotes[num]

    end_paragraph()
    return paragraphs, para_footnotes, para_levels


# ----------------------------------------------------------------------
# 5) Region-spezifische Renderer
# ----------------------------------------------------------------------

VERSAL_RE = re.compile(r"^[A-ZÄÖÜ]{2,}")
CAP_RE = re.compile(r"^[A-ZÄÖÜ][a-zäöü]")


def format_paragraph_txt(para: str, fns: dict[int, str], level: int) -> str:
    """TXT-Modus: Absatz + Fußnoten eingerückt am Absatzende."""
    out = [para]
    for num in sorted(fns):
        out.append(f"{INDENT}[{num}] {fns[num]}")
    return "\n".join(out)


def format_paragraph_md(
    para: str,
    fns: dict[int, str],
    level: int,
    state: dict,
) -> str:
    """
    MD-Modus: [N]-Marker im Absatztext werden zu [^G]-Pandoc-Markern mit
    globaler Numerierung (weil Markdown-Footnote-IDs dokumentweit eindeutig
    sein müssen — Hechbergers Kapitel-Reset bricht das sonst). Die Defs
    werden in state["defs"] gesammelt und am Dokumentende emittiert.
    Überschriften (level > 0) werden mit # voran gesetzt.
    """
    num_map: dict[int, int] = {}

    def repl(m: re.Match) -> str:
        local = int(m.group(1))
        if local not in fns:
            return m.group(0)
        if local not in num_map:
            state["counter"] += 1
            g = state["counter"]
            num_map[local] = g
            state["defs"].append(f"[^{g}]: {fns[local]}")
        return f"[^{num_map[local]}]"

    new_para = PLACED_MARKER_RE.sub(repl, para)

    # Fußnoten, deren Marker im Text nicht gefunden wurden: als hängende
    # Referenz am Absatzende anfügen, damit die Def nicht verwaist bleibt.
    for local in sorted(fns):
        if local in num_map:
            continue
        state["counter"] += 1
        g = state["counter"]
        state["defs"].append(f"[^{g}]: {fns[local]}")
        new_para = new_para.rstrip() + f" [^{g}]"

    if level > 0:
        return ("#" * min(level, 6)) + " " + new_para
    return new_para


def render_main(
    pages: list[Page],
    threshold: int,
    fmt: str,
    state: dict,
    audit: dict[int, list[int]],
    annotator=None,
) -> list[str]:
    paras, fns, levels = reconstruct_body(pages, threshold, audit)
    if annotator is not None:
        paras = [annotator.annotate(p, f) for p, f in zip(paras, fns)]
    if fmt == "md":
        return [
            format_paragraph_md(p, f, lvl, state)
            for p, f, lvl in zip(paras, fns, levels)
        ]
    return [
        format_paragraph_txt(p, f, lvl) for p, f, lvl in zip(paras, fns, levels)
    ]


def render_frontmatter(pages: list[Page]) -> list[str]:
    """Front Matter: Originalzeilen erhalten, pro Seite ein Block."""
    blocks: list[str] = []
    for p in pages:
        if not p.body_lines:
            continue
        marker = f"[S. {p.num}]\n" if p.num >= 0 else ""
        blocks.append(marker + "\n".join(p.body_lines).rstrip())
    return blocks


def render_toc(pages: list[Page]) -> list[str]:
    """Inhaltsverzeichnis komplett auslassen — nur Marker hinterlassen."""
    if not pages:
        return []
    return ["[Inhaltsverzeichnis ausgelassen]"]


def render_entries(pages: list[Page], start_re: re.Pattern[str]) -> list[str]:
    """
    Listenartige Region (Bibliographie, Index, Abkürzungen).
    Ein Eintrag = zusammenhängender Block, der mit start_re beginnt;
    Folgezeilen werden dehyphenated angehängt.
    """
    entries: list[str] = []
    cur: list[str] = []
    pending_hyphen = False
    pending_page: str | None = None

    def flush():
        nonlocal cur, pending_hyphen
        if cur:
            entries.append("".join(cur).rstrip())
        cur = []
        pending_hyphen = False

    def append_seg(seg: str):
        nonlocal pending_hyphen, pending_page
        if not seg:
            return
        if pending_hyphen:
            cur.append(seg)
            pending_hyphen = False
        else:
            if cur:
                cur.append(" ")
            cur.append(seg)
        if pending_page is not None:
            cur.append(" " + pending_page)
            pending_page = None

    for p in pages:
        if p.num >= 0:
            pending_page = f"[S. {p.num}]"
        n = len(p.body_lines)
        for i, ln in enumerate(p.body_lines):
            stripped = ln.rstrip()
            if not stripped.strip():
                continue
            if start_re.match(stripped) and not pending_hyphen:
                flush()
            ends_hyphen = (
                len(stripped) >= 2 and stripped.endswith("-")
                and stripped[-2].isalpha()
            )
            if ends_hyphen and i + 1 < n:
                if is_hard_hyphen(stripped, p.body_lines[i + 1]):
                    ends_hyphen = False
            content = stripped[:-1] if ends_hyphen else stripped
            append_seg(content)
            pending_hyphen = ends_hyphen
    flush()
    return entries


def render_book(
    pages: list[Page], threshold: int, fmt: str = "txt", annotator=None
) -> tuple[str, dict[int, list[int]]]:
    """Pages in Quellreihenfolge nach Modus gruppieren und passend rendern.

    Liefert das gerenderte Dokument sowie ein Audit-Dict mit Seiten, auf
    denen mindestens eine Fußnoten-Def keinen Marker im Body hatte.
    """
    out_blocks: list[str] = []
    state: dict = {"counter": 0, "defs": []}
    audit: dict[int, list[int]] = {}
    i = 0
    while i < len(pages):
        mode = pages[i].mode
        j = i
        while j < len(pages) and pages[j].mode == mode:
            j += 1
        group = pages[i:j]

        if mode == "main":
            out_blocks.extend(render_main(group, threshold, fmt, state, audit, annotator))
        elif mode in ("frontmatter", "raw"):
            out_blocks.extend(render_frontmatter(group))
        elif mode == "toc":
            out_blocks.extend(render_toc(group))
        elif mode == "entries-versal":
            out_blocks.extend(render_entries(group, VERSAL_RE))
        else:
            out_blocks.extend(render_frontmatter(group))

        i = j

    result = "\n\n".join(out_blocks).rstrip()
    if fmt == "md" and state["defs"]:
        result += "\n\n" + "\n\n".join(state["defs"])
    return result + "\n", audit


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main(src_dir: str, out_path: str, fmt: str | None = None) -> None:
    src = Path(src_dir)
    files = sorted(src.glob("[0-9]*.txt"))
    print(f"Lese {len(files)} Seiten aus {src}…", file=sys.stderr)

    if fmt is None:
        fmt = "md" if out_path.lower().endswith(".md") else "txt"
    print(f"Ausgabeformat: {fmt}", file=sys.stderr)

    raw_texts = [f.read_text(encoding="utf-8", errors="replace") for f in files]

    # Kolumnentitel und Fußzeilen seitenweit entfernen, bevor parse_page läuft.
    from scriptor.reflow.running_elements import strip_running_elements
    cleaned, headers, footers = strip_running_elements(raw_texts)
    if headers:
        print(f"Running-Header entfernt ({len(headers)}): {headers[:3]}", file=sys.stderr)
    if footers:
        print(f"Running-Footer entfernt ({len(footers)}): {footers[:3]}", file=sys.stderr)

    pages: list[Page] = []
    for text in cleaned:
        pg = parse_page(text)
        if pg is not None:
            pages.append(pg)

    assign_modes(pages)
    mode_counts = Counter(p.mode for p in pages)
    print(f"Modus-Verteilung: {dict(mode_counts)}", file=sys.stderr)

    threshold, hist = calibrate_threshold(pages)
    print(f"Kalibrierung (nur main): Schwellwert ≤ {threshold} Zeichen", file=sys.stderr)
    print(f"  Top-Zeilenlängen: {hist.most_common(5)}", file=sys.stderr)

    clean_output, _ = render_book(pages, threshold, fmt)
    Path(out_path).write_text(clean_output, encoding="utf-8")
    print(f"Geschrieben: {out_path}", file=sys.stderr)

    # Annotierter Master (immer, Option 3) — zweiter Render mit Annotator.
    from scriptor.reflow.confidence import Annotator
    annotator = Annotator()
    review_output, _ = render_book(pages, threshold, fmt, annotator=annotator)
    op = Path(out_path)
    review_path = op.with_name(f"{op.stem}.review{op.suffix}")
    review_path.write_text(review_output, encoding="utf-8")
    print(
        f"Annotierter Master: {review_path}  "
        f"({len(annotator.annotations)} unsichere FN)",
        file=sys.stderr,
    )

    # Erweitertes Audit-Sidecar aus den Annotationen + Lauf-Zusammenfassung.
    from scriptor.reflow.confidence import render_audit
    total_fn_defs = sum(len(p.footnotes) for p in pages)
    audit_text = render_audit(
        annotator.annotations, total_fn_defs, len(pages), out_path
    )
    audit_path = op.with_suffix(op.suffix + ".audit.txt")
    audit_path.write_text(audit_text, encoding="utf-8")
    print(
        f"Audit: {len(annotator.annotations)} unsichere FN → {audit_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    fmt = None
    if "--format" in args:
        i = args.index("--format")
        fmt = args[i + 1]
        del args[i : i + 2]
    if len(args) >= 2:
        main(args[0], args[1], fmt)
    else:
        main(".", "Staufer_und_Welfen_reflow.txt", fmt)
