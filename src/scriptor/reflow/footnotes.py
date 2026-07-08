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

# Footnote definition at the start of a line: "NN) Text…".
FOOTNOTE_RE = re.compile(r"^(\d{1,3})\)\s?(.*)$")
# Marker in the finished body: already replaced with [NN] — recognised during reflow.
PLACED_MARKER_RE = re.compile(r"\[(\d{1,3})\]")

# OCR often delivers footnote markers as Unicode superscripts. Before marker
# detection we normalise these to ASCII digits.
SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
    "⁸": "8", "⁹": "9",
})


def substitute_markers(body_lines: list[str], footnotes: dict[int, str]) -> list[str]:
    """
    Replaces footnote markers in the body with '[NN]'. Two-pass procedure:

      Pass 1 (safe): NN glued directly onto a word/punctuation character.
                     — e.g. 'word64', 'said"64', 'annals-/64' (after dehyph.)
      Pass 2 (fallback): NN separated from the previous token by whitespace.
                     — e.g. 'led" 30.'

    Each footnote number is consumed only once (sequentially). If both
    passes would find a marker for the same NN, pass 1 wins.
    False positives on numbers in the running text are largely avoided,
    because only numbers from the footnotes set count as candidates at all.
    """
    if not footnotes or not body_lines:
        return body_lines

    # Process the body as one string with separators — newlines are \S-free,
    # so word boundaries are preserved. Split again after substitution.
    SEP = "\n"
    body = SEP.join(body_lines)
    consumed: set[int] = set()

    # Pass 1: glued on
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=\S){num}(?=$|[^\w])", re.MULTILINE)
        new_body, n = pat.subn(f" [{num}]", body, count=1)
        if n > 0:
            body = new_body
            consumed.add(num)

    # Pass 2: separated by whitespace — only for numbers not yet consumed
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=\s){num}(?=$|[^\w])", re.MULTILINE)
        new_body, n = pat.subn(f"[{num}]", body, count=1)
        if n > 0:
            body = new_body
            consumed.add(num)

    return body.split(SEP)
