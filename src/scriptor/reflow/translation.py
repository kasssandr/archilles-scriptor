"""Übersetzungs-Profil (Etappe 2c): Markdown-Master -> übersetzungsreifes MD.

Reiner String-Postprozessor (kein I/O). Schützt nicht zu übersetzende Elemente
mit <dnt>…</dnt>-Tags und entfernt offene Confidence-Flags (strip-and-pass).
Siehe docs/superpowers/specs/2026-06-21-uebersetzungs-profil-design.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable

DNT_OPEN = "<dnt>"
DNT_CLOSE = "</dnt>"

# http(s):// oder www.… bis Whitespace/'<'. Trailing-Satzzeichen wird beim
# Wrappen abgetrennt (siehe protect_urls), nicht hier.
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<]+", re.IGNORECASE)

# Titel-Anführungspaare: deutsch „…“, gerade "…", Guillemets »…«.
QUOTE_PAIRS = [("„", "“"), ('"', '"'), ("»", "«")]

# Pandoc-Fußnoten-Definitionszeile (einzeilig).
FN_DEF_RE = re.compile(r"^\[\^\d+\]:")

# Confidence-Flags der 2-B-Schicht: [?FN:…] / [??FN:…] (optionales führendes Space).
FLAG_RE = re.compile(r" ?\[\?\??FN:[^\]]*\]")

# Bestehende <dnt>…</dnt>-Spanne (für das Transformieren nur außerhalb davon).
_DNT_SPAN_RE = re.compile(r"<dnt>.*?</dnt>", re.DOTALL)
_URL_TRAIL = ".,;:!?)]"


def strip_flags(text: str) -> str:
    """Entfernt offene Confidence-Flags (strip-and-pass, §9-Q2). Body bleibt
    unverändert; verwaiste Fußnoten-Defs bleiben erhalten."""
    return FLAG_RE.sub("", text)


def strip_dnt(text: str) -> str:
    """Entfernt die DNT-Tags, behält den Innentext (Round-Trip-Inverse zum
    Wrappen). Das führt Archillator nach der Übersetzung aus."""
    return text.replace(DNT_OPEN, "").replace(DNT_CLOSE, "")


def _transform_outside_dnt(text: str, transform: Callable[[str], str]) -> str:
    """Wendet ``transform`` nur auf die Textteile *außerhalb* bestehender
    <dnt>…</dnt>-Spannen an; vorhandene Spannen bleiben unangetastet. So sind
    alle protect_*-Funktionen idempotent und erzeugen keine Verschachtelung."""
    out: list[str] = []
    last = 0
    for m in _DNT_SPAN_RE.finditer(text):
        out.append(transform(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(transform(text[last:]))
    return "".join(out)


def protect_urls(text: str) -> str:
    """Taggt URLs mit <dnt>…</dnt>. Trailing-Satzzeichen bleibt außerhalb des
    Tags. Überspringt bereits getaggte URLs."""
    def _wrap(m: re.Match) -> str:
        url = m.group(0)
        trail = ""
        while url and url[-1] in _URL_TRAIL:
            trail = url[-1] + trail
            url = url[:-1]
        return f"{DNT_OPEN}{url}{DNT_CLOSE}{trail}"

    return _transform_outside_dnt(text, lambda s: URL_RE.sub(_wrap, s))


def protect_quoted(text: str) -> str:
    """Taggt Titel in Anführungszeichen (alle QUOTE_PAIRS) mit <dnt>…</dnt>.
    Nur außerhalb bestehender Tags; idempotent."""
    def _wrap(seg: str) -> str:
        for open_q, close_q in QUOTE_PAIRS:
            pattern = re.escape(open_q) + "[^" + re.escape(close_q) + "]*" + re.escape(close_q)
            seg = re.sub(
                pattern,
                lambda m: f"{DNT_OPEN}{m.group(0)}{DNT_CLOSE}",
                seg,
            )
        return seg

    return _transform_outside_dnt(text, _wrap)


def prepare_translation(markdown: str) -> str:
    """Master-Markdown -> übersetzungsreifes MD: Flags strippen; URLs überall
    taggen; auf Fußnoten-Def-Zeilen zusätzlich Titel in Anführungszeichen
    taggen. Idempotent; strukturelle Pandoc-Marker bleiben unangetastet."""
    text = strip_flags(markdown)
    out_lines: list[str] = []
    for line in text.split("\n"):
        line = protect_urls(line)
        if FN_DEF_RE.match(line):
            line = protect_quoted(line)
        out_lines.append(line)
    return "\n".join(out_lines)


BRIEFING = """Übersetzungs-Briefing für Archillator
=====================================
Dieses Dokument ist für die LLM-Übersetzung vorbereitet.

1. Übersetze den Fließtext in die Zielsprache.
2. Text innerhalb von <dnt>…</dnt> wörtlich und unverändert belassen — niemals
   übersetzen, umstellen oder normalisieren. Geschützt sind so referenzierte
   Werk-/Artikeltitel, bibliografische Verweise und URLs.
3. Auch ungetaggte referenzierte Literaturtitel, Eigennamen und bibliografische
   Verweise verbatim belassen (besonders im Fußnotenapparat) — im Zweifel nicht
   übersetzen. Bibliografische Präzision hat Vorrang vor Vollständigkeit.
4. Pandoc-Strukturen unverändert übernehmen: Fußnotenmarker [^N], Fußnoten-
   Definitionen [^N]:, Seitenmarker [S. NN].
5. Nach der Übersetzung die Tags <dnt> und </dnt> entfernen, den Innentext
   behalten.
"""
