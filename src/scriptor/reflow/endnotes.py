"""Endnotes: the notes a volume collects behind its text (variant c).

Footnotes are read page by page: the definition stands under the text it
annotates, and ``parse_page`` finds both on one page. Endnotes do not. Meisel,
*Der Mythus der herrschenden Klasse* (1962), prints 776 of them on pp.
395-425, counted afresh for each chapter under heads like "Zum 3. Kapitel";
Van der Toorn, *Scribal Culture* (2007), prints its own under "Notes",
"Introduction", "1. Books That Are Not Books". Read as footnotes, each notes
page is a page of definitions whose markers are nowhere on it, and the body's
markers find no definition on theirs.

Two steps, after the regions are known (the notes part is ``region ==
"notes"``):

* ``read_notes`` takes the notes part apart into *collections*, each a run of
  notes counted from 1, with the head the volume sets over it. The count is the
  witness: a line opens a note only as the number the count expects next, and a
  count that starts again at 1 opens the next collection -- where it really
  starts again, and not where a note's own line happens to begin "1 Bd.".
* ``bind`` finds each note's marker in the text before the notes part, walking
  the collections in order and the markers in reading order, every marker after
  the one before it. A note it finds goes into the ``footnotes`` of the page its
  marker stands on, and from there the footnote path renders it like any other
  (PREPARED_FORMAT_SPEC §4.3): one number across the document, the definitions
  at its end. A note whose marker is lost goes to the page of the next marker
  of its collection that was found, where the hanging-reference rule puts its
  synthetic anchor before that marker -- the last place the lost one can have
  stood.

The notes part keeps its heads and its page markers; the notes leave it for
the definitions (decided 2026-10-27). The page a note is printed on travels
with the note into the notes sidecar.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from scriptor.reflow.footnotes import PLACED_MARKER_RE
from scriptor.reflow.headings import mark_placed, read_mark
from scriptor.reflow.regions import region_of_heading

# "12 Text", "12. Text", "12) Text": a note opening. Which of them is one is
# the count's to say -- and the volume's: it sets its notes in one of these
# shapes, and a list inside a note in another (Meisel, note F.1: "1 Zu Moscas
# Befürchtungen …", then "1. Die Zahl der Eliten …", "2. Wenn es …").
NOTE_START = re.compile(r"^(\d{1,3})([.)]?)\s+(\S.*)$")
# A printed marker as the OCR read it: "[11]", "[ 1]", "[46.]".
_PRINTED = re.compile(r"\[\s?(\d{1,3})\.?\s?\]")
# A sentence closes here; a head never does. Quotes and brackets may follow.
_CLOSED = re.compile(r"[.!?;:,][\"'»«“”‘’)\]]*$")
# A head is short. Measured against the notes part's full lines -- the
# measure it is set in, not the median, which a part of short notes ("Ibid.")
# pulls down to the length of a head -- and never against less than a short
# measure would be.
_HEAD_SHARE = 0.75
_MEASURE_QUANTILE = 0.8
_MIN_MEASURE = 40
# How many notes a collection may open before the OCR sets its head: Meisel's
# reads "1 HK, S. 348." / "2 …" / "3 …" / "Zum 10. Kapitel" / "4 …".
_HEAD_LATE = 4
# How many markers in a row may be lost before the walk takes a number for
# the text's own: a page's worth of them on a bad scan.
_MAX_LOST = 6
# A marker glued to its word: "question.1", "Bibel23". Not after a digit, a
# colon or a dash: "12:9" is a verse, "29–30" a range.
_GLUED = re.compile(r"(?<=[^\s\d:\-–—/\[(])(\d{1,3})(?=$|[^\w:\-–—/\]])")
# A raised marker the OCR set as a line of its own.
_ALONE = re.compile(r"^(\d{1,3})$")


@dataclass
class EndNote:
    number: int
    text: str
    page: int            # position in ``pages`` of the page the note begins on


@dataclass
class Collection:
    title: str | None    # the head over it, verbatim; None where the volume sets none
    notes: list[EndNote] = field(default_factory=list)


@dataclass
class NotesPart:
    collections: list[Collection]
    # What stays on each notes page: the text before the first note (the
    # part's own heading, a list of abbreviations) and the collection heads.
    skeleton: dict[int, list[str]]


def _closed(text: str) -> bool:
    return bool(_CLOSED.search(text.rstrip()))


def _join(parts: list[str]) -> str:
    from scriptor.reflow.core import dehyphenate_join
    return dehyphenate_join(parts).strip()


def read_notes(stream: list[tuple[int, str]]) -> NotesPart:
    """The notes part, from its lines in reading order: (page position, line).

    A line that does not open the expected note continues the one before it.
    A "1" where the count expects more opens a collection only if the next
    opening after it is a 2 -- not the number the old count expects, which
    makes it a line of the note running ("1 Bd.", "1 (1925)"). A head is a short
    line closing no sentence, standing where a collection starts: before its
    first note, or -- the OCR's reading order -- among its first few, after a
    note that closed. A note-shaped line whose next opening is a 1 is a head
    as well, whatever its number: Van der Toorn sets "2. Authorship in
    Antiquity" after note 67 of the chapter before, and "1. Books That Are Not
    Books" directly over "1. From biblion …".
    """
    lines = [(pos, read_mark(line)[0].strip()) for pos, line in stream]
    lines = [(pos, s) for pos, s in lines if s]
    if not lines:
        return NotesPart([], {})
    lengths = sorted(len(s) for _pos, s in lines)
    width = max(lengths[int(len(lengths) * _MEASURE_QUANTILE)], _MIN_MEASURE)
    shapes = Counter(m.group(2) for _pos, s in lines if (m := NOTE_START.match(s)))
    shape = shapes.most_common(1)[0][0] if shapes else ""
    starts = [(i, int(m.group(1))) for i, (_pos, s) in enumerate(lines)
              if (m := NOTE_START.match(s)) and m.group(2) == shape]

    def next_start(i: int, numbers: set[int] | None = None) -> int | None:
        for j, n in starts:
            if j > i and (numbers is None or n in numbers):
                return n
        return None

    def head_shaped(s: str) -> bool:
        return (len(s) <= _HEAD_SHARE * width and not _closed(s)
                and not s[:1].islower())

    collections: list[Collection] = []
    skeleton: dict[int, list[str]] = {}
    pending: list[tuple[int, str]] = []        # head candidates not yet judged
    parts: list[str] = []                       # lines of the note running
    note: EndNote | None = None
    expected = 1

    def close_note() -> None:
        nonlocal note, parts
        if note is not None:
            note.text = _join(parts)
            collections[-1].notes.append(note)
        note, parts = None, []

    def flush_pending() -> None:
        # Not heads after all: lines of the note running, or of the text
        # before the first note.
        nonlocal pending
        for pos, s in pending:
            if note is not None:
                parts.append(s)
            else:
                skeleton.setdefault(pos, []).append(s)
        pending = []

    def open_collection(pos: int) -> None:
        # The part's own heading may stand directly over the first head
        # ("Notes" / "Introduction"): it stays the part's, not the collection's.
        # So does what stands on earlier pages -- the part's half-title,
        # "Notes • Selected Bibliography • Index".
        last = pending[-1][0] if pending else None
        own = [(p, s) for p, s in pending
               if p != last or region_of_heading(s) == "notes"]
        rest = [(p, s) for p, s in pending if (p, s) not in own]
        for p, s in own:
            skeleton.setdefault(p, []).append(s)
        for p, s in rest:
            skeleton.setdefault(p, []).append(mark_placed(s, 2))
        pending.clear()
        collections.append(Collection(" ".join(s for _p, s in rest) or None))

    for i, (pos, s) in enumerate(lines):
        m = NOTE_START.match(s)
        n = int(m.group(1)) if m else None
        if m and m.group(2) != shape:
            # The other shape opens only the note the count expects, and only
            # where the next note confirms it: Meisel's single "70. Dorso"
            # between "69 Dorso" and "71 A. a. O.".
            if not (collections and n == expected
                    and next_start(i) in (expected + 1, None)):
                n = None
        if n is not None and n == 1 and next_start(i) == 1 and head_shaped(m.group(3)):
            # "1. Books That Are Not Books" over "1. From biblion …".
            close_note()
            pending.append((pos, s))
            continue
        # A 1 starts the count again where a head stands over it, or where
        # the old count does not go on after it: Van der Toorn's introduction
        # has a single note, and the next opening is a chapter's 1.
        restarts = n == 1 and (
            not collections or bool(pending)
            or (expected > 1 and next_start(i, {1, 2, expected}) != expected))
        if restarts:
            close_note()
            open_collection(pos)
            note, parts, expected = EndNote(1, "", pos), [m.group(3)], 2
            continue
        if n is not None and n == expected and collections:
            close_note()
            note, parts, expected = EndNote(n, "", pos), [m.group(3)], n + 1
            continue
        if head_shaped(s) and (note is None or _closed(parts[-1])):
            if next_start(i) == 1:
                pending.append((pos, s))
                continue
            if (collections and collections[-1].title is None
                    and len(collections[-1].notes) < _HEAD_LATE
                    and next_start(i) == expected):
                # The head the OCR read after the collection's first notes.
                collections[-1].title = s
                skeleton.setdefault(pos, []).append(mark_placed(s, 2))
                continue
        flush_pending()
        if note is not None:
            parts.append(s)
        else:
            skeleton.setdefault(pos, []).append(s)
    flush_pending()
    close_note()
    return NotesPart(collections, skeleton)


@dataclass
class Bound:
    """What ``bind`` did: per collection, (title, notes, found, hanging)."""
    form: str                                    # "printed" | "glued" | "none"
    rows: list[tuple[str | None, int, int, int]] = field(default_factory=list)
    unbound: int = 0                             # notes left in the notes part

    @property
    def found(self) -> int:
        return sum(r[2] for r in self.rows)

    @property
    def hanging(self) -> int:
        return sum(r[3] for r in self.rows)


def _candidates(pages, scope: list[int], form: str):
    """(page position, line index, start, end, number) of every marker of
    ``form`` in reading order. A printed "[N]" the page's own footnotes claim
    is theirs."""
    for pos in scope:
        page = pages[pos]
        for k, line in enumerate(page.body_lines):
            text = read_mark(line)[0]
            if form == "printed":
                for m in _PRINTED.finditer(text):
                    # A marker the page's own footnotes claim is theirs -- unless
                    # the footnote is empty: Meisel p. 332 has a stray "1" at its
                    # foot, which the printed "[1]" above made into a note 1 with
                    # nothing in it. The notes part has the text.
                    if not page.footnotes.get(int(m.group(1)), "").strip():
                        yield pos, k, m.start(), m.end(), int(m.group(1))
            else:
                alone = _ALONE.match(text.strip())
                if alone:
                    yield pos, k, None, None, int(alone.group(1))
                    continue
                for m in _GLUED.finditer(text):
                    yield pos, k, m.start(1), m.end(1), int(m.group(1))


def _walk(collections: list[Collection], candidates) -> dict[tuple[int, int], tuple]:
    """{(collection, number): candidate} -- each collection's markers in order,
    every one after the one before it. The next collection begins at a 1 once
    the one running has found anything, and only where the next marker after
    that 1 is a 2 rather than the number the running count expects: on bare
    text a 1 glued to a word is the commonest number there is."""
    candidates = list(candidates)
    found: dict[tuple[int, int], tuple] = {}
    c, expected = 0, 1

    def next_of(i: int, wanted: set[int]) -> int | None:
        return next((cand[4] for cand in candidates[i + 1:] if cand[4] in wanted), None)

    for i, cand in enumerate(candidates):
        if c >= len(collections):
            break
        n = cand[4]
        size = len(collections[c].notes)
        # A collection begins with its 1, and a number past the one expected
        # stands for lost markers only where the count goes on from it: on
        # bare text a stray "5" before the chapter opens took Van der Toorn's
        # ninth collection for one that had lost its first four.
        skips = n > expected and (expected == 1 or next_of(i, {n + 1, expected}) == expected)
        # And its 1 is the last 1 before its 2: a stray one on the chapter
        # before's last page put Van der Toorn's 9.1 three pages early.
        early = n == expected == 1 and size > 1 and next_of(i, {1, 2}) == 1
        if expected <= n <= min(size, expected + _MAX_LOST) and not skips and not early:
            found[(c, n)] = cand
            expected = n + 1
            if expected > size:
                c, expected = c + 1, 1
        elif (n == 1 and expected > 1 and c + 1 < len(collections)
              and next_of(i, {2, expected}) in (2, None)):
            c += 1
            found[(c, 1)] = cand
            expected = 2
            if expected > len(collections[c].notes):
                c, expected = c + 1, 1
    return found


def bind(pages, part: NotesPart, scope: list[int]) -> Bound:
    """Hang each note on the page its marker stands on (see the module).

    ``scope`` are the positions of the pages the notes annotate, in reading
    order. The printed form ("[N]") is tried first; where it finds fewer than
    half the notes the walk is repeated on markers glued to their words.
    """
    collections = part.collections
    total = sum(len(c.notes) for c in collections)
    if not total:
        return Bound("none")
    form = "printed"
    found = _walk(collections, _candidates(pages, scope, "printed"))
    if 2 * len(found) < total:
        glued = _walk(collections, _candidates(pages, scope, "glued"))
        if len(glued) > len(found):
            form, found = "glued", glued
    if not found:
        return Bound("none", unbound=total)

    # Write the markers into the text as the footnote path reads them, right
    # to left within a line so that the offsets stay true: a glued one set off
    # from its word, a printed one the OCR bent ("[ 1]", "[46.]") set straight.
    edits: dict[tuple[int, int], list[tuple]] = {}
    for cand in found.values():
        edits.setdefault((cand[0], cand[1]), []).append(cand)
    for (pos, k), cands in edits.items():
        line = pages[pos].body_lines[k]
        mark_prefix = line[:len(line) - len(read_mark(line)[0])]
        text = line[len(mark_prefix):]
        for _pos, _k, start, end, n in sorted(cands, key=lambda c: -(c[2] or 0)):
            if start is None:
                text = f"[{n}]"
            elif form == "glued":
                text = f"{text[:start]} [{n}]{text[end:]}"
            else:
                text = f"{text[:start]}[{n}]{text[end:]}"
        pages[pos].body_lines[k] = mark_prefix + text

    bound = Bound(form)
    for c, coll in enumerate(collections):
        placed = sorted(n for (cc, n) in found if cc == c)
        hanging = 0
        if not placed:
            bound.unbound += len(coll.notes)
            bound.rows.append((coll.title, len(coll.notes), 0, 0))
            continue
        for note in coll.notes:
            if note.number in placed:
                pos = found[(c, note.number)][0]
            else:
                later = [n for n in placed if n > note.number]
                pos = found[(c, later[0] if later else placed[-1])][0]
                hanging += 1
            page = pages[pos]
            if page.footnotes.get(note.number, "").strip():
                # The page already defines this number -- its own footnote, or
                # a note of another collection whose chapter ends here. One
                # page cannot carry two notes of one number; this one stays
                # where it is printed.
                bound.unbound += 1
                _keep_in_part(pages, note)
                continue
            page.footnotes[note.number] = note.text
            printed_on = pages[note.page]
            page.endnotes[note.number] = (coll.title, printed_on.label, printed_on.index)
        bound.rows.append((coll.title, len(coll.notes), len(placed),
                           hanging))
    for c, coll in enumerate(collections):
        if not any(cc == c for (cc, _n) in found):
            for note in coll.notes:
                _keep_in_part(pages, note)
    return bound


def _keep_in_part(pages, note: EndNote) -> None:
    """A note no marker claims stays on its page of the notes part, as the
    line it was printed as."""
    pages[note.page].body_lines.append(f"{note.number} {note.text}")


def apply_skeleton(pages, positions: list[int], part: NotesPart) -> None:
    """The notes pages keep their heads and the text before the first note;
    everything else on them has left for the definitions."""
    for pos in positions:
        page = pages[pos]
        page.body_lines = list(part.skeleton.get(pos, []))
        page.footnotes = {}
        page.fn_continuation = None
        page.notes_part = True
