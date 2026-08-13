"""Page labels: the page identifier as it is *printed* on the page.

Contract with archilles (``docs/WATCHDOG_AND_WIKI.md`` §II.5): the citable page
is the printed label — ``xiv`` or ``312`` — not a physical page index. The label
travels verbatim into the ``[p. …]`` marker and into TOC anchors.

``decode_label`` exists only to *order* pages (sequence scoring, sorting). It
must never be used to identify one: roman ``xiv`` and arabic ``14`` decode to
the same number but are different pages, and keying anchors on the decoded value
makes a table-of-contents link jump into the preface.
"""

from __future__ import annotations

import re

# A page marker in rendered output. The label is anything up to the bracket, so
# roman labels survive the round trip.
PAGE_MARKER_RE = re.compile(r"\[p\. ([^\]]+)\]")

ARABIC_RE = re.compile(r"^\d{1,4}$")

# Canonical roman numeral, lowercase only, at least two characters.
#
# Lowercase, because frontmatter page labels are lowercase by strong convention
# (i, ii, … xiv). Insisting on it keeps uppercase division numbers in running
# heads ("BOOK II", "CHAPTER XIV") from being read as a page label — and a line
# read as a page label is *deleted from the body* by ``parse_page``.
#
# At least two characters, for the same reason: a lone "l" is far more often an
# OCR misreading of "1" than roman 50, and a lone "i" is more often an artifact
# than page one. The price is that pages i, v and x carry no marker. Losing a
# marker is recoverable; deleting a line of the author's text is not.
ROMAN_RE = re.compile(
    r"^(?=[mdclxvi])"
    r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$"
)
MIN_ROMAN_LEN = 2

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

# A label paired with a running-head title, at either edge of the line:
# "146 WILHELM HEIL" / "L'ORIGINE DE LA NOBLESSE 23" / "xiv PREFACE".
_LABEL_TOKEN = r"\d{1,4}|[mdclxvi]{2,}"
_HEAD_LEAD = re.compile(rf"^({_LABEL_TOKEN})\s+(.+)$")
_HEAD_TRAIL = re.compile(rf"^(.+?)\s+({_LABEL_TOKEN})$")


def _roman_to_int(s: str) -> int:
    values = [_ROMAN_VALUES[c] for c in s]
    total = 0
    for i, v in enumerate(values):
        total += -v if i + 1 < len(values) and v < values[i + 1] else v
    return total


def decode_label(label: str) -> int | None:
    """Ordinal value of a printed page label, or None if it is not one.

    For ordering only — see the module docstring on why this is not an identity.
    """
    s = label.strip()
    if ARABIC_RE.match(s):
        n = int(s)
        return n if 1 <= n <= 9999 else None
    if len(s) >= MIN_ROMAN_LEN and ROMAN_RE.match(s):
        return _roman_to_int(s)
    return None


def style_of(label: str) -> str | None:
    """Which numbering system a label is written in, or None if it is not one.

    The pagination plan models a stretch of pages as one numbering system, so a
    roman label inside an arabic stretch is a contradiction rather than a value
    to compare. Uppercase roman is accepted here although ``detect_page_label``
    refuses it: the detector's refusal protects the body text from having a
    running head deleted, while this classifier is only ever asked about a label
    somebody already produced -- and the PDF catalogue does state "XIV".
    """
    s = label.strip()
    if not s:
        return None
    if ARABIC_RE.match(s):
        return "arabic" if 1 <= int(s) <= 9999 else None
    if len(s) >= MIN_ROMAN_LEN and ROMAN_RE.match(s.lower()):
        return "roman-lower" if s.islower() else "roman-upper"
    return None


def is_running_head_like(text: str) -> bool:
    """True if ``text`` looks like a running header/footer (mostly uppercase
    letters, few lowercase) rather than ordinary prose."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.7


def detect_page_label(line: str) -> str | None:
    """Detect the printed page label on a single line, conservatively.

    Accepts a line that is nothing but a label, or a label at either edge paired
    with a running-head-like title ("146 WILHELM HEIL"). Returns the label
    verbatim, so casing and numbering system survive. Returns None for ordinary
    prose (a leading year, a chapter number) — reporting no page is always the
    safe answer, because the caller removes a detected label from the body.

    The head-paired branch is a fallback for inputs where running-element
    removal does not fire. In the full pipeline ``strip_running_elements`` runs
    before ``parse_page`` and usually removes a recurring running head, page
    label and all. It still helps short articles whose head does not recur often
    enough to be detected as a running element.
    """
    s = line.strip()
    if not s:
        return None

    if decode_label(s) is not None:
        return s

    for rx, token_group, text_group in ((_HEAD_LEAD, 1, 2), (_HEAD_TRAIL, 2, 1)):
        m = rx.match(s)
        if m and is_running_head_like(m.group(text_group)):
            token = m.group(token_group)
            if decode_label(token) is not None:
                return token
    return None
