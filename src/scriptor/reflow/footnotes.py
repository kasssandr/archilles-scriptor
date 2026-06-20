"""Footnote markers: detection patterns and placement.

Owns *what a footnote marker/definition looks like* (the regexes and the
superscript-digit normalisation) and *how a marker is placed into the body*
(``substitute_markers``). Split out of ``core.py`` (Etappe 2-A) so the
confidence layer (Etappe 2-B) has a home next to the marker logic it extends.
Behaviour is identical to the previous in-``core`` implementation — this is a
move, not a change.
"""

from __future__ import annotations

import re

# Fußnoten-Definition am Zeilenanfang: "NN) Text…".
FOOTNOTE_RE = re.compile(r"^(\d{1,3})\)\s?(.*)$")
# Marker im fertigen Body: bereits durch [NN] ersetzt — wird beim Reflow erkannt.
PLACED_MARKER_RE = re.compile(r"\[(\d{1,3})\]")

# OCR liefert Fußnotenmarker oft als Unicode-Superscripts. Vor der
# Marker-Erkennung normalisieren wir diese in ASCII-Ziffern.
SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
    "⁸": "8", "⁹": "9",
})


def substitute_markers(body_lines: list[str], footnotes: dict[int, str]) -> list[str]:
    """
    Ersetzt Fußnoten-Marker im Body durch '[NN]'. Zwei-Pass-Verfahren:

      Pass 1 (sicher): NN direkt an ein Wort/Punktuationszeichen geklebt.
                       — z.B. 'wort64', 'sagte"64', 'Annalen-/64' (nach dehyph.)
      Pass 2 (Fallback): NN durch Leerzeichen vom vorigen Token getrennt.
                       — z.B. 'geführt" 30.'

    Jede Fußnotennummer wird nur einmal verbraucht (sequentiell). Wenn beide
    Pässe einen Marker für dasselbe NN finden würden, gewinnt Pass 1.
    Falsche Treffer auf Zahlen im Fließtext werden weitgehend vermieden,
    weil nur Nummern aus dem footnotes-Set überhaupt als Kandidaten gelten.
    """
    if not footnotes or not body_lines:
        return body_lines

    # Body als ein String mit Trennern verarbeiten — Newlines sind \S-frei,
    # also bleiben Wortgrenzen erhalten. Nach Substitution wieder splitten.
    SEP = "\n"
    body = SEP.join(body_lines)
    consumed: set[int] = set()

    # Pass 1: angeklebt
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=\S){num}(?=$|[^\w])", re.MULTILINE)
        new_body, n = pat.subn(f" [{num}]", body, count=1)
        if n > 0:
            body = new_body
            consumed.add(num)

    # Pass 2: durch Whitespace abgesetzt — nur für noch nicht konsumierte Nummern
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=\s){num}(?=$|[^\w])", re.MULTILINE)
        new_body, n = pat.subn(f"[{num}]", body, count=1)
        if n > 0:
            body = new_body
            consumed.add(num)

    return body.split(SEP)
