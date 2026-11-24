"""Small helpers for phrasing CLI messages and sidecar texts, and the one
spacing convention every Markdown producer shares."""

from __future__ import annotations

import re


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    """``1 page`` / ``2 pages`` — number and noun agree in grammatical number.

    Only pass ``plural_form`` when the simple ``+"s"`` doesn't work
    (e.g. ``reference without a definition``).
    """
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural_form or singular + 's'}"


# A footnote reference in the body; a definition (``[^N]:``) is not one.
_REF = r"\[\^[^\]\s]+\](?!:)"
# After these a reference sits close: an opening bracket.
_OPENS = "([{„‚"
# Before these it sits close: punctuation and closing brackets and quotes.
_CLOSES = ".,;:!?)]}”’"
# These open in one language and close in another (“ is German closing,
# English opening; » the reverse of «). Next to them the spacing is left as
# the text had it.
_EITHER = "\"'“‘«»"

_BEFORE = re.compile(rf"(?<=[^\s{re.escape(_OPENS + _EITHER)}])[ \t]*({_REF})")
_AFTER = re.compile(
    rf"({_REF})[ \t]*(?=[^\s{re.escape(_CLOSES + _EITHER)}])")
_CLOSE_UP = re.compile(rf"({_REF})[ \t]+(?=[{re.escape(_CLOSES)}]|$)", re.MULTILINE)


def space_note_refs(text: str) -> str:
    """A footnote reference stands as a word of its own: ``Satz. [^5] Weiter``.

    One space before it and one after, the same everywhere in a document, so
    that a reader proofing it — or its translation — sees one form. It sits
    close only where a space would stand wrong: after an opening bracket,
    before punctuation or a closing bracket (``(see p. 4 [^5])``), and at the
    end of a line. A line that begins with a reference keeps its indent.
    """
    text = _BEFORE.sub(r" \1", text)
    text = _AFTER.sub(r"\1 ", text)
    return _CLOSE_UP.sub(r"\1", text)
