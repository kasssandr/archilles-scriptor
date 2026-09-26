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
from dataclasses import dataclass

# A note number has up to four digits: a volume that numbers its notes through
# runs past 999 (Bauer prints 1320), and with three the whole apparatus from
# note 1000 on stayed in the running text. A four-digit number is also what a
# year looks like, though, so it opens a definition only where it continues the
# volume's own numbering -- see ``continues``.
#
# Footnote definition at the start of a line: "NN) Text…".
FOOTNOTE_RE = re.compile(r"^(\d{1,4})\)\s?(.*)$")
# "NN. Text…" — the other common print convention (Zuckerman). Far too frequent
# in running prose (enumerations, years) to trust on bare text: it is only
# applied inside a block the page geometry has already verified as small type.
# OCR drops the space now and then ("5.The theory", Kuijsten p. 3); without it
# the note opens only on a capital or a quotation mark, never on "2017.12".
FOOTNOTE_DOT_RE = re.compile(r"^(\d{1,4})\.(?:\s+|(?=[A-Z“\"‘']))(\S.*)$")
# "NN Text…" — a superscript number the extractor flattened, with nothing but a
# space after it. Requires the space, so a continuation line opening with
# "27, S. 53." or "2017, S. 41" is not mistaken for a definition.
FOOTNOTE_SPACE_RE = re.compile(r"^(\d{1,4})\s+(\S.*)$")
# Marker in the finished body: already replaced with [NN] — recognised during reflow.
PLACED_MARKER_RE = re.compile(r"\[(\d{1,4})\]")

# OCR often delivers footnote markers as Unicode superscripts. Before marker
# detection we normalise these to ASCII digits.
SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
    "⁸": "8", "⁹": "9",
})


# How far past the note read last the next may stand. A page carries a few
# dozen notes at most; a year is centuries away from the note a volume has
# reached.
MAX_NOTE_STEP = 50
# A count that starts again -- per chapter, per part, per page -- starts at 1,
# or at 2 or 3 where the first definition of the new count was unreadable.
RESTART_MAX = 3


def continues(num: int, last: int | None) -> bool:
    """May ``num`` open a page's first note, after ``last``, the highest note
    the volume has read so far?

    Below 1000 it may: a count restarts per chapter, part or page, and the
    first note of a block is where it does. From 1000 on the number has to
    continue the volume's numbering -- note 999 was read, so 1000 is a note,
    but in a volume that has reached note 45 the "1958);" that opens a
    bibliography line is a year (L'Empire chrétien: 53 false notes, A/B of
    19.9.). The highest note, not the last one: a single misreading must not
    set the course for every page after it.
    """
    return num < 1000 or (last is not None and last < num <= last + MAX_NOTE_STEP)


def misread(num: int, prev: int) -> bool:
    """Could ``num`` be the note after ``prev`` with a digit lost or misread?

    OCR drops and swaps the digits of a small-set number: Le trasformazioni
    prints 151 after 150, and the text layer says "15 '". The next number with
    one digit lost, or with one digit wrong, is that note -- from two digits
    on: a single digit is a fragment of too many numbers to say anything.
    """
    s = str(num)
    if num == prev or len(s) < 2:
        return False
    for nxt in (prev + 1, prev + 2):
        t = str(nxt)
        if len(t) == len(s) + 1 and (t.startswith(s) or t.endswith(s)):
            return True
        if len(t) == len(s) and sum(a != b for a, b in zip(s, t)) == 1:
            return True
    return False


def follows(num: int, prev: int) -> bool:
    """May ``num`` open a note after note ``prev`` of the same block?

    It continues the count -- above ``prev``, at most MAX_NOTE_STEP past it,
    or the next note with a digit misread -- or starts it again (a chapter
    that begins mid-page). Anything else is the next line of note ``prev``,
    opening with a number that is no note: a page of a citation ("BGH GRUR
    2017, S. 390," / "393 Rn. 10 ff."), a day before its month ("... vom" /
    "17. April 2019"), a year ("(Paris," / "1930); M. Pellegrino"). Over the
    21 page models some 475 such lines had been read as notes (19.9.).

    The rule holds within a block and not across pages (user, 19.9.: the
    continuation rule for every number). Carried from page to page it broke
    the moment one number was misread -- a caption, an OCR slip -- and every
    page after lost its apparatus: A comemoração kept 24 of 117 note blocks,
    Bauer 248 of 1320 notes (A/B of 19.9.).
    """
    return (prev < num <= prev + MAX_NOTE_STEP or num <= RESTART_MAX
            or misread(num, prev))


def definition_start(line: str) -> re.Match | None:
    """The shape of a definition start, before the numbering is asked."""
    return (FOOTNOTE_RE.match(line)
            or FOOTNOTE_DOT_RE.match(line)
            or FOOTNOTE_SPACE_RE.match(line))


def note_starts(lines: list[str], last: int | None = None,
                shape=definition_start) -> list[tuple[int, int]]:
    """(line index, number) of the lines of a block that open a note.

    Every line shaped like a definition start is a candidate. The block's
    notes are its longest run of candidates in which each ``follows`` the one
    before and the first may open the page (``continues`` after the volume's
    highest note ``last``); every other candidate is the next line of a note.
    The run, not the first candidate, decides: Bauer's block that opened with
    the tail of a note ("2. Aufl. 2018, S. 12.") took it for note 2, and 249,
    250, 251 followed nothing. Among runs of one length, the one that
    continues the volume's count wins, then the earlier one. No number opens
    two notes of one run -- the second would overwrite the first.
    """
    cands: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = shape(line)
        if m:
            cands.append((i, int(m.group(1))))
    if not cands:
        return []
    # best[j]: (length of the best run ending at j, it continues the volume,
    # -start), back[j]: the candidate before j in that run.
    best: list[tuple[int, bool, int] | None] = [None] * len(cands)
    back: list[int | None] = [None] * len(cands)
    for j, (_idx, num) in enumerate(cands):
        if continues(num, last):
            best[j] = (1, last is not None and last < num <= last + MAX_NOTE_STEP, -j)
        for k in range(j):
            if best[k] is None or not follows(num, cands[k][1]):
                continue
            used, p = set(), k
            while p is not None:
                used.add(cands[p][1])
                p = back[p]
            if num in used:
                continue
            score = (best[k][0] + 1, best[k][1], best[k][2])
            if best[j] is None or score > best[j]:
                best[j], back[j] = score, k
    end = max((j for j in range(len(cands)) if best[j] is not None),
              key=lambda j: best[j], default=None)
    run: list[tuple[int, int]] = []
    while end is not None:
        run.append(cands[end])
        end = back[end]
    return run[::-1]


def match_definition(line: str, last: int | None = None) -> re.Match | None:
    """Definition start inside a size-verified footnote block.

    Three print conventions: "NN)", "NN." and a bare "NN " — the last one is
    what a superscript number extracts to when the publisher sets no
    punctuation after it (Nomos, De Gruyter). It is the loosest of the three
    and is only ever consulted inside a block the geometry has already
    verified as small type; on bare running text it would match any sentence
    that opens with a number. ``last`` is the highest note read so far; a
    four-digit number has to continue it (``continues``).
    """
    m = definition_start(line)
    return m if m and continues(int(m.group(1)), last) else None


def definition_numbers(lines: list[str], last: int | None = None) -> list[int]:
    """The notes a run of lines opens, in reading order (``note_starts``)."""
    return [num for _i, num in note_starts(lines, last)]


# A footnote block is set measurably smaller than the body. OCR text layers
# estimate sizes from glyph height, so the values scatter; both bounds must
# hold before a line counts as small (Zuckerman: 7.5pt against 9.0pt body).
SMALL_TYPE_MIN_DELTA = 1.0    # points below the body size
SMALL_TYPE_MAX_RATIO = 0.92   # fraction of the body size
# A running head, a folio or a download watermark below the apparatus is
# short. Body-sized prose of any length under a small run means the run was
# a set-off quotation, not the footnote block.
FURNITURE_MAX_CHARS = 30


@dataclass
class SmallTypeSplit:
    body: list[str]    # body lines, a peeled bottom page label included
    notes: list[str]   # the small-type block, a leading continuation included
    split_at: int = 0  # how many of ``body``'s lines keep their source index
                       # (the peeled label tail behind them does not)


def dominant_size(
    lines: list[str], sizes: list[float | None]
) -> float | None:
    """The dominant type size, weighted by line length (characters)."""
    weights: dict[float, int] = {}
    for text, size in zip(lines, sizes):
        if size is None:
            continue
        weights[size] = weights.get(size, 0) + len(text)
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0]


def split_small_type_block(
    lines: list[str],
    sizes: list[float | None],
    body_size: float | None = None,
    last_note: int | None = None,
) -> SmallTypeSplit | None:
    """Cut the trailing small-type footnote block off a page, or return None.

    ``body_size`` is the document-wide dominant size — calibrate it over all
    pages, not this one: on a note-heavy page the footnotes outweigh the body,
    and a page-local mode would flip to the footnote size and see nothing
    small. Without it the page's own dominant size serves as fallback.
    ``last_note`` is the highest note the pages before have opened; a
    four-digit definition has to continue it (``continues``).

    The cut is conservative: it needs measured sizes, a contiguous small run at
    the bottom of the page, and at least one definition start ("NN)" / "NN.")
    inside that run. A small block without a definition (a caption, a small-set
    quotation) is left alone. A bare page label at the very bottom is peeled
    first and stays with the body, so label detection still sees it.
    """
    from scriptor.reflow.pagelabel import detect_page_label

    if len(lines) != len(sizes) or not lines:
        return None
    if body_size is None:
        body_size = dominant_size(lines, sizes)
    if body_size is None:
        return None

    def small_size(s: float | None) -> bool:
        return (
            s is not None
            and body_size - s >= SMALL_TYPE_MIN_DELTA
            and s <= body_size * SMALL_TYPE_MAX_RATIO
        )

    def small(i: int) -> bool:
        return small_size(sizes[i])

    # Peel bare page labels (and blank lines) off the very bottom; they sit
    # below the footnote block and belong to the body for label detection.
    bottom = len(lines)
    tail: list[str] = []
    while bottom > 0 and (
        not lines[bottom - 1].strip()
        or detect_page_label(lines[bottom - 1]) is not None
    ):
        tail.insert(0, lines[bottom - 1])
        bottom -= 1

    # Then work upwards through the runs of small type until one holds a
    # definition. Peeling folios alone is not enough: what sits below the
    # apparatus varies by publisher — a running head, a download watermark —
    # and any one of them would otherwise mask the block behind it.
    end = bottom
    while True:
        while end > 0 and not small(end - 1):
            end -= 1
        if end == 0:
            return None
        start = end
        while start > 0 and small(start - 1):
            start -= 1
        if start == 0:
            # The whole page is small type: without body lines above, this could
            # as well be a small-set contents page or preface whose "N. Title"
            # lines would be swallowed as definitions. Too risky — leave it.
            return None
        if definition_numbers(lines[start:end], last_note):
            break
        end = start          # this run carries no definition; look further up

    # Below the block there may be page furniture, but never running text: a
    # small run with body-sized prose underneath it is a set-off quotation in
    # the middle of the page, not the apparatus at its foot.
    for i in range(end, bottom):
        if not small(i) and len(lines[i].strip()) > FURNITURE_MAX_CHARS:
            return None

    # A contents set smaller than its heading is a run of "N. Title" lines in
    # small type, the very shape of an apparatus -- both of Kuijsten's contents
    # pages went into the notes whole, and with them every chapter title.
    from scriptor.reflow.toc import is_contents_heading
    if any(is_contents_heading(ln) for ln in lines[:start]):
        return None

    # The fixed ratio decides which lines are small, not where the block begins.
    # OCR guesses a size from glyph height, and a body line can land just under
    # the threshold -- on screenshots set at a different scale per page the last
    # body line above the apparatus measured 11.6pt against a 13pt body and 9pt
    # notes (Kuijsten p. 3). A line above the block's first note that sits nearer
    # the body than the notes' own size is body text; the notes' size is read
    # from the first note down, where the block is certainly apparatus.
    first = note_starts(lines[start:end], last_note)
    if first:
        top = start + first[0][0]
        block = sorted(s for s in sizes[top:end] if s is not None)
        mid = block[len(block) // 2]
        while start < top and abs(body_size - sizes[start]) < abs(sizes[start] - mid):
            start += 1

    notes = lines[start:end]
    if not definition_numbers(notes, last_note):
        return None
    return SmallTypeSplit(
        body=lines[:start] + lines[end:bottom] + tail, notes=notes, split_at=start
    )


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

    # Pass 1: glued on. The character before the marker must not be a digit —
    # a printed marker glues to a letter or punctuation ('fall.4', 'word64'),
    # never to another digit. Without this, the last digit of a year births a
    # footnote ('August 754' -> 'August 75 [4]', Zuckerman p. 39) while the
    # genuine marker goes empty.
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=[^\s\d]){num}(?=$|[^\w])", re.MULTILINE)
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
