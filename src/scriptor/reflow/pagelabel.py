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


# Ornament a typesetter sets around a folio: rules, dots, dashes, brackets.
# Masones prints ". 50.", others "— 50 —". The rule belongs to the page's
# design, the number to the page.
_ORNAMENT = " \t.,-–—·•*_()[]"

# What the relaxed reading takes for a number. Three digits, not four: no corpus
# volume prints a four-digit folio (the largest is the Oxford Handbook's 894),
# while four digits at the edge of a page have twice been an imprint year that
# founded a segment of its own -- A comemoração "2020", L'Empire "1972".
_RELAXED_LABEL = r"\d{1,3}|[mdclxvi]+|[MDCLXVI]+"
_RELAXED_ALONE = re.compile(rf"^({_RELAXED_LABEL})$")
_RELAXED_LEAD = re.compile(rf"^({_RELAXED_LABEL})\s+(.+)$")
_RELAXED_TRAIL = re.compile(rf"^(.+?)\s+({_RELAXED_LABEL})$")

# A running head is short and reads as a title. Prose that merely begins with a
# number -- a drop cap the extractor lost, "1 he fall of the city …" -- runs on
# in more words and carries the punctuation of a sentence; a bibliography line
# carries digits of its own ("Bruxelles, 1936 (Subsidia Hagiographica, XXII)").
_HEAD_MAX_CHARS = 60
_HEAD_MAX_WORDS = 6
_NOT_IN_HEAD = re.compile(r"[,;()\[\]\d]")


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
    somebody already produced -- and the PDF catalogue does state "XIV". A lone
    roman character passes for the same reason, and it has to: it is the pages
    i, v and x, and classifying them as nothing at all would make them
    contradict every plan they belong to. Kept in step with ``ordinal_of``, so
    that whatever can be ordered can also be classified.
    """
    s = label.strip()
    if not s:
        return None
    if ARABIC_RE.match(s):
        return "arabic" if 1 <= int(s) <= 9999 else None
    if ROMAN_RE.match(s.lower()):
        return "roman-lower" if s.islower() else "roman-upper"
    return None


def ordinal_of(label: str) -> int | None:
    """The ordinal a label denotes, in whatever case it is written.

    ``decode_label`` refuses versal roman, and refuses a lone roman character,
    for the reason its module docstring gives: it is asked about lines of the
    author's text, where "BOOK II" must not become a page and a stray "l" must
    not become 50. The pagination is asked about a label somebody has already
    produced -- the PDF catalogue states "XIV", a volume may set its front
    matter versal, and page "x" of Artificial Humanities is a page. There the
    case and the length are matters of spelling, not of identity, and a reading
    that cannot be ordered is a reading that silently does not count.
    ``style_of`` is its counterpart on the classifying side.
    """
    s = label.strip().lower()
    if ARABIC_RE.match(s):
        n = int(s)
        return n if 1 <= n <= 9999 else None
    if ROMAN_RE.match(s):
        return _roman_to_int(s)
    return None


_ROMAN_NUMERALS = (
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
)


def strip_ornament(text: str) -> str:
    """The line without the rule the typography set around it."""
    return text.strip().strip(_ORNAMENT)


def encode_label(value: int, style: str) -> str | None:
    """Write an ordinal in the numbering system a stretch of pages runs in.

    For positions **nobody observed**. A label somebody observed travels
    verbatim and is never re-encoded, or "XIV" comes back as "xiv" and the
    volume is cited in a form it never printed.

    This is what the pagination lacked while it could only write back arabic
    labels: an arabic label is its own ordinal written out, so a stretch of
    roman front matter had its gaps left open however well attested it was. La
    masonería is the volume that made the omission cost something -- 64 printed,
    counted pages, of which the second round can read 43 and the remaining 21
    are enclosed between them.
    """
    if value < 1:
        return None
    if style == "arabic":
        return str(value)
    if style not in ("roman-lower", "roman-upper"):
        return None
    out = []
    left = value
    for size, numeral in _ROMAN_NUMERALS:
        while left >= size:
            out.append(numeral)
            left -= size
    roman = "".join(out)
    return roman if style == "roman-lower" else roman.upper()


def read_label_relaxed(line: str) -> str | None:
    """Read a folio off a line the geometry has already vouched for.

    ``detect_page_label`` is narrow because the caller deletes the line it reads
    a label out of, so each of its refusals protects the author's text. This
    reading answers a different question: a witness has put this line at the
    height and the edge where the volume has been printing folios all along, no
    character is removed on its word alone, and the fit weighs what it says
    against every other page. The vocabulary therefore opens up exactly where
    printers differ from the narrow rule:

    versal front matter          La masonería "XII", Gli Actus "XVIII INTRODUZIONE"
    a single roman character     Artificial Humanities "x" over its illustrations
    a title set in ordinary case Themistios "XII Inhaltsverzeichnis"
    a number dressed by the rule Masones ". 50."

    Narrower in one respect, see ``_RELAXED_LABEL``: four digits are refused
    here, because at this end of the page they are an imprint year far more
    often than a folio.

    The label comes back verbatim. "XII" stays versal -- that is what the page
    prints, and a citation has to match the page.
    """
    s = strip_ornament(line)
    if not s:
        return None

    m = _RELAXED_ALONE.match(s)
    if m:
        return s if ordinal_of(s) is not None else None

    for rx, token_group, text_group in ((_RELAXED_LEAD, 1, 2), (_RELAXED_TRAIL, 2, 1)):
        m = rx.match(s)
        if not m:
            continue
        token, text = m.group(token_group), m.group(text_group).strip(_ORNAMENT)
        if ordinal_of(token) is None or not _reads_as_a_head(text):
            continue
        return token
    return None


def _reads_as_a_head(text: str) -> bool:
    """Is this the title beside a folio, rather than a line of the book?"""
    return (
        len(text) <= _HEAD_MAX_CHARS
        and len(text.split()) <= _HEAD_MAX_WORDS
        and sum(1 for c in text if c.isalpha()) >= 2
        and not _NOT_IN_HEAD.search(text)
    )


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
