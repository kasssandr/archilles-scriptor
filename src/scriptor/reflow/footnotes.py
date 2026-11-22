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
from collections import Counter
from dataclasses import dataclass

# A note number has up to four digits: a volume that numbers its notes through
# runs past 999 (Bauer prints 1320), and with three the whole apparatus from
# note 1000 on stayed in the running text. A four-digit number is also what a
# year looks like, though, so it opens a definition only where it continues the
# volume's own numbering -- see ``continues``.
#
# Footnote definition at the start of a line: "NN) Text…", or "NNx)" / "NN x)"
# for a note added after note NN (``NoteNo``). Group 1 is read by ``note_no``.
FOOTNOTE_RE = re.compile(r"^(\d{1,4}(?: ?[a-z])?)\)\s?(.*)$")


class NoteNo(int):
    """The number of an added note, "12f": a note a volume set in after its
    note 12 without renumbering the ones behind it (Pückert's *Aniane und
    Gellone*, Kern's *Gottesgnadentum*, both around 1900).

    It counts as its number -- 12f carries the count no further than 12 did,
    so the arithmetic on the volume's highest note reads it as 12 -- and it is
    a note of its own: it compares, hashes and prints with its letter, after
    12 and before 13. Only an added note is a NoteNo; every other note stays a
    plain int, so a volume without added notes runs the code it always ran.

    The trap: ``NoteNo(12, "f") == 12`` is False although ``int()`` of it is
    12. Code that asks for the count says ``int(n)``.
    """

    letter: str

    def __new__(cls, number: int, letter: str) -> "NoteNo":
        self = super().__new__(cls, number)
        self.letter = letter
        return self

    def _key(self) -> tuple[int, str]:
        return int(self), self.letter

    @staticmethod
    def _key_of(other: int) -> tuple[int, str]:
        return int(other), getattr(other, "letter", "")

    def __eq__(self, other):
        return self._key() == self._key_of(other) if isinstance(other, int) else NotImplemented

    def __ne__(self, other):
        return self._key() != self._key_of(other) if isinstance(other, int) else NotImplemented

    def __lt__(self, other):
        return self._key() < self._key_of(other) if isinstance(other, int) else NotImplemented

    def __le__(self, other):
        return self._key() <= self._key_of(other) if isinstance(other, int) else NotImplemented

    def __gt__(self, other):
        return self._key() > self._key_of(other) if isinstance(other, int) else NotImplemented

    def __ge__(self, other):
        return self._key() >= self._key_of(other) if isinstance(other, int) else NotImplemented

    def __hash__(self) -> int:
        return hash(self._key())

    def __str__(self) -> str:
        return f"{int(self)}{self.letter}"

    def __repr__(self) -> str:
        return f"NoteNo({int(self)}, {self.letter!r})"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)


_NOTE_NO = re.compile(r"(\d+) ?([a-z])?")


def note_no(text: str) -> int:
    """The note a definition start names: "12" -> 12, "12f" or "12 f" ->
    NoteNo(12, "f")."""
    m = _NOTE_NO.fullmatch(text)
    return NoteNo(int(m.group(1)), m.group(2)) if m.group(2) else int(m.group(1))


def added_after(num: int, prev: int | None) -> bool:
    """May the added note ``num`` open behind note ``prev``? Only behind its own
    note or an earlier addition to it: 12 -> 12a, 12e -> 12f. A letter behind
    any other number is a reference broken over the line ("Bl. 197a)", "78b)"
    of a Stephanus page, "V. 43b)") or a folio ("90 v)")."""
    return prev is not None and int(prev) == int(num) and prev < num
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
# "NN Text…" on bare text, or "NN" alone on its line where the OCR read the
# column of note numbers apart from the notes ("3" / "4" / "Franz Overbeck,
# …" / "Eberhard Vischer, …", Taubes p. 182). Only ever trusted where the
# count or a marker vouches for the number (``witnessed_block_start``).
# Not "92 c) ihrerseits den
# Klöstern …": Aniane marks sub-notes so, and a line opening with one is prose
# behind its marker, which the count (91 -> 92) would have taken for a note.
FOOTNOTE_BARE_RE = re.compile(r"^(\d{1,3})(?:\s+(?![a-z]\))|$)(.*)$")
# Marker in the finished body: already replaced with [NN] — recognised during reflow.
PLACED_MARKER_RE = re.compile(r"\[(\d{1,4})\]")

# OCR often delivers footnote markers as Unicode superscripts. Before marker
# detection we normalise these to ASCII digits.
SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
    "⁸": "8", "⁹": "9",
})

# A note marker glued to its word: "question.1", "Bibel23", 'said"64'. The one
# rule, for the footnote path and the endnotes alike. Never after a digit or a
# space: a printed marker glues to a letter or a mark, and the last digit of a
# year is no note ("August 754" would give note 4, Zuckerman p. 39). Beyond
# that, what the volumes taught, each an exclusion that can be named:
#
# * ``digit_period`` -- not after a digit's period: "2.1 Social Robots" and
#   "2.6.1" number sections (*Artificial Humanities*).
# * ``digit_comma`` -- not after a digit's comma: "(14,1,1)" is Isidor's
#   book, chapter and section, "(2Tim 2,1)" a verse; read as markers "1",
#   Fried's *Karl der Große* p. 85 started its count again.
# * ``joiner`` -- not after a colon, a dash, a slash or an opening bracket,
#   nor before a dash, a slash or a closing bracket: "12:9" is a verse,
#   "29–30" a range, "[12]" a marker already placed (Van der Toorn).
# * ``digit_range`` -- the narrow form of ``joiner``: not after a digit's dash
#   or slash. "14–20", "S. 58–60", "1198/99" are a range and a double year.
# * ``digit_colon`` -- the other narrow form: not after a digit's colon,
#   "Joh 12:9", "(4:2)".
# * ``colon_digit`` -- not before a colon that a digit follows, as in a
#   verse; before any other colon it stands: Fried p. 261 glues note 2 to
#   "Seele2: Eine".
#
# The footnote path does not take ``joiner``: behind a word a colon or a dash
# carries real markers ("following terms:7", Ando; "bezeugt:42", Wolf); the
# A/B of November 2026 measured it there. The digit's period, comma and colon
# hold there because of ``RAISED`` (page.py): a real marker behind "312." or
# "1147," is set raised, the page sets it apart, and the mark stands between
# the punctuation and the number -- "312.<RAISED>186" is never "digit, period,
# number". What is left bare behind them is a section, a reference or a verse
# ("HE 3, 18,5", Pouderon, where each took a note number from its marker).
# The same mark sets a raised number apart from a digit of the text:
# "1150<RAISED>46" reads as glued.
GLUED_EXCLUSIONS = frozenset({"digit_period", "digit_comma", "joiner",
                              "digit_range", "digit_colon", "colon_digit"})
# Which of them hold on the footnote path. The endnotes take them all: a notes
# part is read on bare text, where nothing but the marker's shape says what
# it is.
FOOTNOTE_EXCLUSIONS = GLUED_EXCLUSIONS - {"joiner"}


def glued_marker(numbers=None, exclude: frozenset[str] = GLUED_EXCLUSIONS) -> re.Pattern:
    """The pattern of a glued marker; group 1 is its number.

    ``numbers`` limits it to those numbers (any of up to three digits
    otherwise); ``exclude`` names the exclusions above that apply.
    """
    unknown = set(exclude) - GLUED_EXCLUSIONS
    if unknown:
        raise ValueError(f"unknown exclusions: {sorted(unknown)}")
    if numbers is None:
        number = r"\d{1,3}"
    else:
        number = "|".join(str(n) for n in sorted(set(numbers), reverse=True))
    before = r"\s\d" + (r":\-–—/\[(" if "joiner" in exclude else "")
    behind = ((r"(?<!\d\.)" if "digit_period" in exclude else "")
              + (r"(?<!\d,)" if "digit_comma" in exclude else "")
              + (r"(?<!\d[\-–—/])" if "digit_range" in exclude else "")
              + (r"(?<!\d:)" if "digit_colon" in exclude else ""))
    barred = r"\w" + (r"\-–—/\]" if "joiner" in exclude else "")
    if "colon_digit" in exclude:
        after = rf"(?=$|[^{barred}:]|:(?!\d))"
    else:
        after = rf"(?=$|[^{barred}])"
    return re.compile(rf"(?<=[^{before}]){behind}({number}){after}", re.MULTILINE)


# An asterisk set as a note marker: glued to the word before it, standing
# alone. "*kuningaz" opens a word and stays the author's. A rule of its own
# beside the glued number: a star carries no count to check it by.
ASTERISK_MARKER = re.compile(r"(?<=[^\s\d*\\])\*(?=\s|$)")


def witnessed_block_start(lines: list[str], last_read: int | None = None) -> int | None:
    """Where a page's footnote block begins, on bare text: the first line
    "NN Text" (or "NN" alone) whose number a witness vouches for.

    Without type sizes the only convention trusted on bare text was "NN)";
    a volume that sets "NN Text" kept its whole apparatus in the running text
    (Taubes, Vom Kult zur Kultur: 2 notes found in 383 pages), and only the
    notes after the first came apart, wherever a short line happened to end
    a paragraph. Two witnesses stand in for the geometry:

    * the count -- NN continues the note read last on the pages before
      (``last_read``), one lost number allowed;
    * the marker -- the body above prints NN glued to a word or a mark
      ("Streitschrift1", "Gegenwart“2"), the shape the raised number takes
      once flattened. A number after a space ("S. 2", "Bd. 13") is no
      marker.

    A line opening with a number nothing vouches for is prose ("2 Bände
    …"), and the first line of a page is never a note. A number alone on its
    line is as often the raised marker itself, which the OCR set on a line of
    its own ("…aufzuklären bleibt.\"" / "41", Taubes p. 38): it opens the
    block only where no line below opens the same note -- with its text, or
    alone again in the column of numbers the OCR read apart from the notes
    ("work.2" / "23" / "IV" … "23" / "24" / "See above, note 9.", Study and
    Knowledge p. 90). Asking only for the text, 83 such markers had opened
    the block in the upper half of their page, and the body below them went
    into the apparatus.
    """
    for i, line in enumerate(lines):
        m = FOOTNOTE_BARE_RE.match(line)
        if not m or i == 0:
            continue
        num = int(m.group(1))
        if not m.group(2).strip() and any(
                (b := FOOTNOTE_BARE_RE.match(below)) and int(b.group(1)) == num
                for below in lines[i + 1:]):
            continue
        if last_read is not None and last_read < num <= last_read + 2:
            return i
        marker = glued_marker([num], FOOTNOTE_EXCLUSIONS)
        if any(marker.search(above) for above in lines[:i]):
            return i
    return None


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

    An added note ("12f") never opens a page on this question: the highest
    note says nothing about which note was read last (``added_after``).
    """
    if isinstance(num, NoteNo):
        return False
    return num < 1000 or (last is not None and last < num <= last + MAX_NOTE_STEP)


def misread(num: int, prev: int) -> bool:
    """Could ``num`` be the note after ``prev`` with a digit lost or misread?

    OCR drops and swaps the digits of a small-set number: Le trasformazioni
    prints 151 after 150, and the text layer says "15 '". The next number with
    one digit lost, or with one digit wrong, is that note -- from two digits
    on: a single digit is a fragment of too many numbers to say anything.
    """
    s = str(num)
    if num == prev or len(s) < 2 or isinstance(num, NoteNo):
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

    An added note follows only its own note (``added_after``), and starts no
    count.
    """
    if isinstance(num, NoteNo):
        return added_after(num, prev)
    return counts_on(num, prev) or num <= RESTART_MAX


def counts_on(num: int, prev: int) -> bool:
    """Is ``num`` the count carried on from ``prev``, not a fresh start?"""
    if isinstance(num, NoteNo):
        return added_after(num, prev)
    return prev < num <= prev + MAX_NOTE_STEP or misread(num, prev)


def leaves_bracket_open(line: str) -> bool:
    """Does ``line`` open a round bracket it does not close? Then a "28)"
    opening the line below closes it: the rest of a reference broken over the
    line, not a note -- "(Röm. 11," / "28)" (Taubes), "(SS. XIII," / "608):"
    and "(Weihn. 818/819: vgl. Anm." / "19), durch" (Pückert). The line before
    only: asked of everything since the note before, a note that left its own
    bracket open would keep the next one from opening (Pückert pp. 50, 170).
    A note's own number "11)" closes nothing, and is not counted. And the
    bracket left open has to open something: a reference carries words or
    numbers behind it, a bare "(=" on a line of its own is the OCR's noise,
    and the "47)" below it a note (Pückert p. 224)."""
    line = _OWN_NUMBER.sub("", line, count=1)
    opened: list[int] = []
    for k, ch in enumerate(line):
        if ch == "(":
            opened.append(k)
        elif ch == ")" and opened:
            opened.pop()
    return any(re.search(r"\w", line[k + 1:]) for k in opened)


# The number a note opens with, "11)" or "12f)".
_OWN_NUMBER = re.compile(r"^\s*\d{1,4}(?: ?[a-z])?\)")


def definition_start(line: str) -> re.Match | None:
    """The shape of a definition start, before the numbering is asked."""
    return (FOOTNOTE_RE.match(line)
            or FOOTNOTE_DOT_RE.match(line)
            or FOOTNOTE_SPACE_RE.match(line))


def _shape_kind(line: str) -> int:
    """Which print convention opens ``line``: "NN)", "NN." or a bare "NN "."""
    if FOOTNOTE_RE.match(line):
        return 0
    return 1 if FOOTNOTE_DOT_RE.match(line) else 2


def note_starts(lines: list[str], last: int | None = None,
                shape=definition_start, last_read: int | None = None,
                ) -> list[tuple[int, int]]:
    """(line index, number) of the lines of a block that open a note.

    Every line shaped like a definition start is a candidate. The block's
    notes are its longest run of candidates in which each ``follows`` the one
    before and the first may open the page (``continues`` after the volume's
    highest note ``last``; an added note "12e" only behind ``last_read``, the
    last note of the pages before, when that is 12 or 12a–12d); every other
    candidate is the next line of a note. A line below one that leaves a
    bracket open is no candidate (``leaves_bracket_open``).
    The run, not the first candidate, decides: Bauer's block that opened with
    the tail of a note ("2. Aufl. 2018, S. 12.") took it for note 2, and 249,
    250, 251 followed nothing. Among runs of one length, the one that
    continues the volume's count wins, then the earlier one. No number opens
    two notes of one run -- the second would overwrite the first.
    """
    cands: list[tuple[int, int]] = []
    kinds: list[int] = []
    for i, line in enumerate(lines):
        m = shape(line)
        # Only a number set "N)" can close a bracket: "46 Thietmar" and "3.
        # ISOCRATE" open their notes behind a note that left its own bracket
        # open (Wolf p. 406, Pouderon p. 29).
        if m and not (i and FOOTNOTE_RE.match(line) and leaves_bracket_open(lines[i - 1])):
            cands.append((i, note_no(m.group(1))))
            kinds.append(_shape_kind(line) if shape is definition_start else 0)
    if not cands:
        return []

    def carries_volume(num: int) -> bool:
        return last is not None and last < num <= last + MAX_NOTE_STEP

    def opens_volume(num: int) -> bool:
        # Before any note has been read, the count the volume is most likely
        # to begin is its first. Only a tie-break: an excerpt may well open at
        # note 45. Patzold's asterisk note cites "Herrschaft um / 500 //
        # Chlodwigs Welt", and as the earlier of two single candidates "500"
        # beat "1." -- and with the volume at note 500 on its first page,
        # nothing after it could carry the count on.
        return carries_volume(num) or (last is None and num <= RESTART_MAX)

    # The conventions in which this block carries the volume's count on. Where
    # there is one, a count that starts afresh in another convention is a list
    # inside a note, not the notes: Disciplina's note 21 enumerates bishops
    # "1) … 13)" under the notes "21." and "22.", and as the longer run the list
    # took the block (Patzold, 15.11.: 42 notes out of three).
    # Only the punctuated conventions vouch for this. A bare "NN " is what a
    # footer looks like as well: Wolf's apparatus ends in "522 # 18 Hatte
    # Heinrich der Löwe eine Schwester?", the folio carried the count on, and
    # the notes "53"/"15." above it were thrown out as a list (A/B, 16.11.).
    carrying = {kinds[j] for j, (_i, num) in enumerate(cands)
                if carries_volume(num) and kinds[j] != 2}
    # best[j]: (length of the best run ending at j, it continues the volume,
    # -start), back[j]: the candidate before j in that run.
    best: list[tuple[int, bool, int] | None] = [None] * len(cands)
    back: list[int | None] = [None] * len(cands)
    for j, (_idx, num) in enumerate(cands):
        if carrying and kinds[j] not in carrying and not carries_volume(num):
            continue
        if continues(num, last) or (isinstance(num, NoteNo) and added_after(num, last_read)):
            best[j] = (1, opens_volume(num), -j)
        for k in range(j):
            if best[k] is None or not follows(num, cands[k][1]):
                continue
            # A block keeps one print convention: a count that starts again
            # in another one is the line of a note that opens with a number
            # ("p. 106 n." / "3) in finding", Goodman p. 5).
            if kinds[j] != kinds[k] and not counts_on(num, cands[k][1]):
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
    return m if m and continues(note_no(m.group(1)), last) else None


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


# A note continued onto a line that opens with a number: "10 (1889), pp. 302-25"
# under "… In: MIÖG", "12. Jahrhunderts (MGH Schriften 47)" under "… Ein
# Gelehrter des". Read as a note, it took the number ("note 10" after note 7,
# and note 8 below it went into note 10's text) -- six times in Fried's
# Donation of Constantine, where the count alone cannot tell, because 10 may
# follow 7 as well as 8 may. The page tells: the notes there hang their number
# in a column of its own, 17pt left of the text, and a continuation line starts
# where the text does. This mark sets such a line apart for the readers of the
# block that see nothing but text; it is taken off with the line's number
# kept. From the Private Use Area, like the reflow's other marks.
CONTINUES = ""
# How far the notes' own edge has to stand from the continuation lines' -- an em
# of the block's type, which a note number set flush with its text (right-
# aligned: "9" half a digit in from "10") never reaches -- and how near a line
# has to stand to the continuation edge to be on it.
HANG_MIN_EM = 1.0
HANG_ON_EM = 0.25


def hung_continuations(lines: list[str], indents: list[float | None],
                       size: float | None, last: int | None = None) -> set[int]:
    """Lines of a note block shaped like a note's start that continue a note.

    The continuation lines -- those that open no note -- share a left edge.
    Where the block's note starts stand an em or more off it, a line shaped
    like a start that stands on it is a continuation. Only where those off
    the edge are at least as many as those on it: in a block set flush, every
    start stands on the continuation edge, and nothing is said.
    """
    if size is None:
        return set()
    starts = {i for i, ln in enumerate(lines) if definition_start(ln)}
    # Measured below the first start only: what stands above it may be a
    # quotation the small run took along, set in from the text (Libros de no
    # poco sobresalto p. 70, six lines at 73pt over a note continued at 59pt),
    # and it pulled the edge onto the real note 22.
    first = min(starts, default=len(lines))
    rest = [round(x) for i, (ln, x) in enumerate(zip(lines, indents))
            if i > first and i not in starts and ln.strip() and x is not None]
    if not starts or not rest:
        return set()
    edge = Counter(rest).most_common(1)[0][0]
    on = {i for i in starts
          if indents[i] is not None and abs(indents[i] - edge) <= size * HANG_ON_EM}
    off = [i for i in starts
           if indents[i] is not None and abs(indents[i] - edge) >= size * HANG_MIN_EM]
    if not on or len(off) < len(on):
        return set()
    # The count outranks the edge where it vouches outright: the number after
    # the start before it -- or after the volume's last note, for the block's
    # first -- opens its note wherever the scan put it (L'Empire chrétien
    # p. 229: "6. Elu par le Sénat …" / "7. Sur la reconnaissance …", set on
    # the continuation edge, its marker in the text).
    nums = {i: note_no(definition_start(lines[i]).group(1)) for i in starts}
    order = sorted(starts)
    vouched = set()
    for k, i in enumerate(order):
        before = nums[order[k - 1]] if k else last
        if before is not None and nums[i] == before + 1:
            vouched.add(i)
    return on - vouched


# Margin notes that run over the page announce it. Disciplina sets "27, 28 >"
# under the last margin note of a page -- the notes 27 and 28 are on the next
# one -- and opens each there with "< 27."; a note that is *continued* over the
# turn ends in ">" and goes on under "< (73)" or a bare "< 57". The arrows are
# the layout's furniture, and they hide the note number from every definition
# shape: Patzold's 93 notes came out with 16 of them merged into the one before.
_POINTER_LIST = re.compile(r"^\(?\d{1,4}\)?(?:\s*,\s*\(?\d{1,4}\)?)*\s*>$")
_POINTER_TRAIL = re.compile(r"\s+>$")
_POINTER_BARE = re.compile(r"^<\s*\(?\d{1,4}\)?\.?$")
_POINTER_CONTINUED = re.compile(r"^<\s*\(\d{1,4}\)\s*(\S.*)$")
_POINTER_OPENS = re.compile(r"^[<>]\s*(\d{1,4})\.?\s*(?!\d*>)(\S.*)$")
# Two announcements make a habit; one "12 >" might be anything.
POINTER_MIN_LISTS = 2


def drop_note_pointers(reconstructions, body_size: float | None
                       ) -> tuple[int, dict[int, set[int]]]:
    """Take the run-over arrows out of the small-type lines of a volume that
    sets them (see ``_POINTER_LIST``).

    Returns how many lines were touched, and per page (index into
    ``reconstructions``) the notes it announces for the next page -- the
    numbers outside parentheses; "(73)" is a note continued, not one moved.

    Only in small type, and only where the volume shows the habit at least
    ``POINTER_MIN_LISTS`` times: an angle bracket in the body, or in the
    apparatus of an edition, is the author's or the editor's. Lines are edited
    in place or dropped together with their size, indent and emphasis, so the
    parallel lists stay parallel.
    """
    announced: dict[int, set[int]] = {}
    if body_size is None:
        return 0, announced

    def small(s: float | None) -> bool:
        return (s is not None and body_size - s >= SMALL_TYPE_MIN_DELTA
                and s <= body_size * SMALL_TYPE_MAX_RATIO)

    habit = sum(1 for r in reconstructions
                for ln, s in zip(r.lines, r.sizes)
                if small(s) and _POINTER_LIST.match(ln.strip()))
    if habit < POINTER_MIN_LISTS:
        return 0, announced

    touched = 0
    for page, r in enumerate(reconstructions):
        keep: list[int] = []
        for i, (ln, s) in enumerate(zip(r.lines, r.sizes)):
            t = ln.strip()
            if not small(s):
                keep.append(i)
                continue
            if _POINTER_LIST.match(t):
                moved = {int(n) for n in re.findall(r"(?<!\()\b\d{1,4}\b(?!\))", t)}
                if moved:
                    announced.setdefault(page, set()).update(moved)
                touched += 1
                continue
            if _POINTER_BARE.match(t):
                touched += 1
                continue
            m = _POINTER_CONTINUED.match(t)
            if m:
                r.lines[i] = m.group(1)
            elif (m := _POINTER_OPENS.match(t)):
                r.lines[i] = f"{m.group(1)}. {m.group(2)}"
            elif _POINTER_TRAIL.search(t):
                r.lines[i] = _POINTER_TRAIL.sub("", t)
            else:
                keep.append(i)
                continue
            touched += 1
            keep.append(i)
        if len(keep) < len(r.lines):
            r.lines = [r.lines[i] for i in keep]
            r.sizes = [r.sizes[i] for i in keep]
            r.indents = [r.indents[i] for i in keep]
            r.emphases = [r.emphases[i] for i in keep]
    return touched, announced


def pull_announced_notes(fn_blocks: list[list[str] | None],
                         announced: dict[int, set[int]]) -> int:
    """Move the notes a page announced for the next one back to that page.

    Their marker stands in the text of the page that announced them, and a
    marker is only ever looked for among the notes of its own page: Patzold's
    notes 27/28, 32-34 and 74-76 got a synthetic anchor each. What moves is the
    head of the next page's block -- the continuation of the last note, if
    any, and the announced notes after it -- up to the first note that was not
    announced. A block that does not open with them is left as it is.
    Returns the number of notes moved.
    """
    moved = 0
    for page in sorted(announced):
        nums = announced[page]
        if page + 1 >= len(fn_blocks) or not fn_blocks[page + 1]:
            continue
        block = fn_blocks[page + 1]
        starts = note_starts(block, min(nums) - 1)
        if not starts or starts[0][1] not in nums:
            continue
        cut, taken = len(block), 0
        for idx, num in starts:
            if num not in nums:
                cut = idx
                break
            taken += 1
        fn_blocks[page] = (fn_blocks[page] or []) + block[:cut]
        fn_blocks[page + 1] = block[cut:] or None
        moved += taken
    return moved


def split_small_type_block(
    lines: list[str],
    sizes: list[float | None],
    body_size: float | None = None,
    last_note: int | None = None,
    indents: list[float | None] | None = None,
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

    ``indents`` (left edges, parallel to ``lines``) lets the block say which of
    its lines that open with a number continue a note (``hung_continuations``);
    they come back marked ``CONTINUES``.
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
    if indents is not None and len(indents) == len(lines):
        block_sizes = sorted(s for s in sizes[start:end] if s is not None)
        hung = hung_continuations(notes, indents[start:end],
                                  block_sizes[len(block_sizes) // 2] if block_sizes else None,
                                  last_note)
        notes = [CONTINUES + ln if k in hung else ln for k, ln in enumerate(notes)]
    opened = definition_numbers(notes, last_note)
    if not opened:
        return None

    # The apparatus is the foot of a page of text: above it stands running
    # text, or at least the marker of one of its notes (a title's note, on a
    # page that holds nothing else). A page set small under its heading alone
    # is a text set small -- Fried prints his appendix of sources in 9.5 pt
    # against a 10.5 pt body, and the first page of each edition, under its
    # title, went into the notes whole, its numbered paragraphs as notes 1-3.
    def running(i: int) -> bool:
        s = sizes[i]
        large = (s is not None and s - body_size >= SMALL_TYPE_MIN_DELTA
                 and body_size <= s * SMALL_TYPE_MAX_RATIO)
        return (not small(i) and not large
                and len(lines[i].strip()) > FURNITURE_MAX_CHARS)

    if not any(running(i) for i in range(start)):
        marker = glued_marker(opened, FOOTNOTE_EXCLUSIONS)
        if not any(marker.search(ln.translate(SUPERSCRIPT_DIGITS)) for ln in lines[:start]):
            return None
    return SmallTypeSplit(
        body=lines[:start] + lines[end:bottom] + tail, notes=notes, split_at=start
    )


def substitute_markers(body_lines: list[str], footnotes: dict[int, str],
                       loose: bool = True) -> list[str]:
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

    ``loose=False`` narrows pass 2 to a number alone on its line. On bare
    text, where the notes are found by convention and witness rather than by
    type size, a free-standing number inside a line is too often the text's
    own: "(Barth, S. 5)" and "also etwas 5 Jahre nach Fridugis Tod" lost
    their 5 to notes 5 (Taubes, Aniane). Alone on its line it is the raised
    marker the OCR set apart ("…zu vollbringen.'" / "7"). Or it closes a
    bracket nothing opened, "Mönche 12)." (``_spaced_bracket_marker``). A
    note whose marker is none of these is placed at the end of its page
    instead.

    An added note ("12f", ``NoteNo``) is anchored that way too: its marker
    prints as "12f)" after a space, a form no pass reads yet, and a "[12f]"
    in the text is nothing the renderer resolves.
    """
    if not footnotes or not body_lines:
        return body_lines
    footnotes = {k: v for k, v in footnotes.items() if not isinstance(k, NoteNo)}

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
        pat = glued_marker([num], FOOTNOTE_EXCLUSIONS)
        new_body, n = pat.subn(f" [{num}]", body, count=1)
        if n > 0:
            body = new_body
            consumed.add(num)

    # Pass 2: separated by whitespace — only for numbers not yet consumed
    for num in sorted(footnotes.keys()):
        if num in consumed:
            continue
        pat = re.compile(rf"(?<=\s){num}(?=$|[^\w])" if loose else rf"^{num}$",
                         re.MULTILINE)
        new_body, n = pat.subn(f"[{num}]", body, count=1)
        if n == 0 and not loose:
            new_body, n = _spaced_bracket_marker(body, num)
        if n > 0:
            body = new_body
            consumed.add(num)

    return body.split(SEP)


# "Mönche 12)." -- the marker as a volume prints it that sets every one with a
# space and a closing bracket (Pückert, *Aniane und Gellone*).
_SPACED_BRACKET = r"(?<=\S)(?<!\d[.,]) {num}\)(?=$|[^\w])"


def _spaced_bracket_marker(body: str, num: int) -> tuple[str, int]:
    """``body`` with the first "word 12)" for note ``num`` placed as
    "word [12]", and how many were placed (0 or 1).

    On bare text this is the one free-standing number pass 2 trusts inside a
    line: a closing bracket nothing opened. A reference closes one ("(SS. II,
    294)", "(M." / "G. Scr. XV, 199)"), asked over the line before as well,
    the way a note's start is (``leaves_bracket_open``). A number behind a
    digit's period or comma closes a list of them ("No. 262. 296. 310)").
    Pückert: 399 of its numbered notes find their marker so, which hung at
    the end of their page before."""
    for m in re.finditer(_SPACED_BRACKET.format(num=num), body, re.MULTILINE):
        line_start = body.rfind("\n", 0, m.start()) + 1
        before = body[body.rfind("\n", 0, max(line_start - 1, 0)) + 1:m.start()]
        if _bracket_open(before):
            continue
        return body[:m.start()] + f" [{num}]" + body[m.end():], 1
    return body, 0


def _bracket_open(text: str) -> bool:
    """Does ``text`` leave a round bracket open?"""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
    return depth > 0
