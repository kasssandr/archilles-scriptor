"""Where the headings a volume names stand on its pages.

The rule this replaces was "first occurrence in reading order", and it is
right often enough to have survived: where a contents list names a printed
page the edition no longer breaks at, nothing else is left. What it cannot do
is tell a heading from the running head that repeats it. Bauer prints
"B. Gang der Darstellung" at the head of page 23 as furniture and in the
middle of the same page as the heading, and the first occurrence is the wrong
one -- the stripper used to delete both, and the word the running head shared
its line with went with them.

So the search asks the page first (Gliederungsmodell §5.2):

1. every place the title fills whole lines, outside the contents itself, each
   of them noted as standing in the page's head region or below it;
2. on the page the entry names, below the head region: that is the heading;
3. otherwise on the page it names, in the head region: that is the heading --
   the chapter that opens at the top and carries no running head;
4. otherwise the first occurrence after the last heading placed, below the
   head region for preference: the old rule, as the fallback it should be;
5. otherwise nothing is placed and the entry is named in ``unplaced``;
6. every *other* occurrence in a head region is a running head, whatever its
   count -- one repetition is enough once the volume itself names the title;
7. the placed headings rise in the order the list writes them, and an outlier
   falls into ``rejected``;
8. a heading owns as many lines as spell it out, never half a word (§2.4).

A page label the contents itself supplied does not confirm an expected page
(§5.9, question 4): that would be the contents agreeing with itself. There
rules 2 and 3 do not apply and rule 4 decides.

The search itself reads no ``Page``: it runs on the raw channel, the lines as
they stood before the strippers, because that is where a chapter opening still
spells its title out. Two functions touch the document afterwards -- ``apply``
writes the placement onto the lines it found, ``judge_numbering`` decides the
numbered lines no entry placed (§5.4) -- and both say what they decided by
marking the line (``reflow.headings.PLACED``), which is all
``reconstruct_body`` has to read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from statistics import median
from typing import Iterable, Sequence

from scriptor.reflow.headings import mark_placed, read_mark
from scriptor.reflow.heads import HeadCandidates
from scriptor.reflow.outline import HEAD_REGION, fold, folded_spans, similar
from scriptor.structure import (
    SchemeTable,
    is_roman_volume,
    scheme_of,
    table_from,
)

# Below this a "title" is not one: an initial, a stray numeral, a leader dash.
# The same bound the chapter search uses.
MIN_TITLE = 4

# How selective the word is that decides whether a page is worth searching at
# all. A shorter one stands inside too many other words once folded.
_GATE_WORD = 6

# How many headings a list has to have placed before it may declare a numbered
# line *not* a heading (§5.4). Volume 10482 of the G2 (c) sample carries a
# contents of six entries and refused forty lines on their strength, thirty of
# which its outline names as headings; a list that short is not a list of the
# volume's divisions. Bauer places 214, 2484 places 92.
MIN_PLACED_TO_REFUSE = 10

# Of the outline's titles, how many the contents has to name before the outline
# counts as the contents itself and its levels replace the learnt depths
# (Befund §5.1; the threshold is the Befund's, still unmeasured).
SAME_LIST_SHARE = 0.8


@dataclass(frozen=True)
class Want:
    """An entry looking for its place: a contents line or an outline entry."""

    text: str                   # designator and title, as the list prints them
    title: str                  # what the search looks for on the page
    depth: int                  # the volume's own nesting, 1 = coarsest
    page: str | None = None     # the printed page a contents entry names
    pos: int | None = None      # the physical page an outline entry names
    source: str = "contents"    # contents | outline
    region: str | None = None   # the region its title names, if any


@dataclass(frozen=True)
class Found:
    """A place a title fills whole lines."""

    pos: int
    line: int
    n_lines: int
    in_head: bool


@dataclass(frozen=True)
class Placed:
    want: Want
    pos: int
    line: int           # into the page's raw lines
    n_lines: int
    in_head: bool
    rule: int           # which of §5.2's rules placed it
    rank: int           # which occurrence on its side of the head region


@dataclass
class Placement:
    placed: list[Placed] = field(default_factory=list)
    unplaced: list[Want] = field(default_factory=list)
    rejected: list[tuple[Want, str]] = field(default_factory=list)

    def by_position(self) -> dict[int, list[Placed]]:
        out: dict[int, list[Placed]] = {}
        for p in self.placed:
            out.setdefault(p.pos, []).append(p)
        return out


@dataclass
class Sources:
    """The entries of both lists as one, and the table their depths make."""

    wants: list[Want]
    table: SchemeTable
    same_list: bool          # the outline repeats the contents (§5.1)
    matched: int             # outline entries the contents also names


# ── the two lists, made one ────────────────────────────────────────────

def merge(contents: Sequence[Want], outline: Sequence[Want]) -> Sources:
    """The contents and the outline as one list in reading order.

    An outline entry the contents also names is one entry, not two. Which of
    the two then states the depth is the question §5.1 settles: an outline
    that repeats the contents *is* the contents, produced from it by the
    publisher's tools, and its levels are that list's nesting already read
    out -- the one thing a copy does better than the original. Where the two
    lists are not the same list, the contents keeps the depth it was learnt
    with and the outline entry is fitted to it by its level.

    Order comes from both: the contents entries in their order, each outline
    entry the contents lost put back where the outline has it.
    """
    # A wording a volume prints more than once ("IV. Kritische Würdigung",
    # four times in Bauer) needs its occurrences paired off in order, or the
    # second outline entry matches the first contents entry again and both
    # lists contribute the same heading twice.
    by_title: dict[str, list[int]] = {}
    for i, want in enumerate(contents):
        by_title.setdefault(fold(want.title), []).append(i)

    pairs: list[tuple[Want, int | None]] = []
    for o in outline:
        queue = by_title.get(fold(o.title))
        pairs.append((o, queue.pop(0) if queue else None))
    matched = sum(1 for _o, i in pairs if i is not None)
    same_list = bool(outline) and matched >= len(outline) * SAME_LIST_SHARE
    levels = _level_depths(pairs, contents)

    out: list[Want] = []
    last = -1
    for o, i in pairs:
        if i is not None and i > last:
            out.extend(contents[last + 1: i])
            here = contents[i]
            out.append(replace(here, depth=o.depth if same_list else here.depth,
                               pos=o.pos))
            last = i
        else:
            # No contents entry, or one already emitted -- a volume may print
            # the same title twice. Either way it stands here on its own.
            out.append(replace(o, depth=o.depth if same_list else levels(o.depth)))
    out.extend(contents[last + 1:])

    roman = is_roman_volume(w.text for w in out)
    schemes = [scheme_of(w.text, roman)[0] for w in out]
    return Sources(out, table_from([w.depth for w in out], schemes),
                   same_list, matched)


def _level_depths(pairs, contents: Sequence[Want]):
    """outline level -> depth, learnt from the entries both lists name.

    A level nobody matched is answered by the nearest one that was, moved by
    the difference: outline levels and contents depths count the same nesting,
    so what separates two levels separates their depths.
    """
    seen: dict[int, list[int]] = {}
    for o, i in pairs:
        if i is not None:
            seen.setdefault(o.depth, []).append(contents[i].depth)
    known = {lvl: max(set(ds), key=ds.count) for lvl, ds in seen.items()}

    def depth_of(level: int) -> int:
        if level in known:
            return known[level]
        if not known:
            return level
        near = min(known, key=lambda l: (abs(l - level), l))
        return max(1, known[near] + level - near)

    return depth_of


# ── the search ─────────────────────────────────────────────────────────

def _gate(title: str) -> str:
    """The folded word that decides whether a page is worth searching.

    The longest word of the title, where it is long enough to be selective;
    the first word otherwise, as the chapter search does it. A gate is a
    cheap "no" -- OCR may damage the word it picks, and then the title is
    missed, which is the risk the chapter search already runs.
    """
    words = [fold(w) for w in title.split()]
    words = [w for w in words if w]
    if not words:
        return ""
    longest = max(words, key=len)
    return longest if len(longest) >= _GATE_WORD else words[0]


def place(
    entries: Sequence[Want],
    raw_by_pos: dict[int, list[str]],
    labels_by_pos: dict[int, tuple[str | None, str | None]],
    *,
    head_region: int = HEAD_REGION,
    skip: Iterable[int] = (),
) -> Placement:
    """Place every entry, by the rules of §5.2.

    ``raw_by_pos`` is the raw channel: the non-empty lines of each physical
    page before the strippers, keyed by position. ``labels_by_pos`` is what
    the pagination verdict decided, ``(label, source)`` per position.
    ``skip`` are the contents' own pages, where every title stands.
    """
    skipped = set(skip)
    positions = sorted(p for p in raw_by_pos if p not in skipped)
    folded = {p: [fold(line) for line in raw_by_pos[p]] for p in positions}
    joined = {p: "".join(folded[p]) for p in positions}

    by_label: dict[str, list[int]] = {}
    for pos, (label, source) in labels_by_pos.items():
        if label and source != "toc" and pos not in skipped:
            by_label.setdefault(label.strip(), []).append(pos)

    result = Placement()
    cursor = (0, -1)
    for want in entries:
        if len(fold(want.title)) < MIN_TITLE:
            result.rejected.append((want, "title too short to search for"))
            continue
        found = _occurrences(want, positions, folded, joined, head_region)
        if not found:
            result.unplaced.append(want)
            continue
        if want.pos is not None:
            expected = {want.pos}           # the outline states a position
        elif want.page is not None:
            expected = set(by_label.get(str(want.page).strip(), ()))
        else:
            expected = set()                # the list names no page at all
        on_page = [f for f in found if f.pos in expected]
        below = [f for f in on_page if not f.in_head]
        after = [f for f in found if (f.pos, f.line) > cursor]
        outside = [f for f in after if not f.in_head]
        if below:
            pick, rule = below[0], 2
        elif on_page:
            pick, rule = on_page[0], 3
        elif outside:
            pick, rule = outside[0], 4
        elif after:
            pick, rule = after[0], 4
        else:
            result.unplaced.append(want)
            continue
        same_side = [f for f in found
                     if f.pos == pick.pos and f.in_head == pick.in_head]
        result.placed.append(Placed(want, pick.pos, pick.line, pick.n_lines,
                                    pick.in_head, rule, same_side.index(pick)))
        cursor = (pick.pos, pick.line)
    _drop_outliers(result)
    return result


def _occurrences(want: Want, positions, folded, joined, head_region) -> list[Found]:
    gate, needle = _gate(want.title), fold(want.title)
    out: list[Found] = []
    for pos in positions:
        if gate and gate not in joined[pos]:
            continue
        for line, n_lines in folded_spans(folded[pos], needle, opens=True):
            out.append(Found(pos, line, n_lines, line < head_region))
    return out


def _drop_outliers(result: Placement) -> None:
    """Rule 7: the placed headings rise in the order the list writes them.

    Kept: the longest run that does not fall back, ties to the earlier finds.
    What this catches is a title the volume also prints somewhere else -- on
    a part-title page listing the chapters behind it, in a cross-reference --
    where rule 4 had nothing better to go by.
    """
    placed = result.placed
    if len(placed) < 2:
        return
    keys = [(p.pos, p.line) for p in placed]
    best: list[int] = []        # length -> index of that run's last element
    prev = [-1] * len(keys)
    for k, key in enumerate(keys):
        lo, hi = 0, len(best)
        while lo < hi:
            mid = (lo + hi) // 2
            if keys[best[mid]] <= key:
                lo = mid + 1
            else:
                hi = mid
        prev[k] = best[lo - 1] if lo else -1
        if lo == len(best):
            best.append(k)
        else:
            best[lo] = k
    keep: set[int] = set()
    k = best[-1] if best else -1
    while k >= 0:
        keep.add(k)
        k = prev[k]
    result.placed = [p for i, p in enumerate(placed) if i in keep]
    result.rejected.extend((p.want, "out of the order its list is written in")
                           for i, p in enumerate(placed) if i not in keep)


# ── writing the verdict onto the pages ─────────────────────────────────

@dataclass
class Applied:
    """What ``apply`` did to the document, for the run report."""

    marked: int = 0                 # placed entries written onto their line
    joined: int = 0                 # of those, headings that took a second line
    lost: list[Placed] = field(default_factory=list)   # gone from the body
    heads_kept: int = 0             # head lines confirmed as the heading
    heads_removed: int = 0          # head lines the placement did not confirm
    promoted: list[dict] = field(default_factory=list)
    refused: list[dict] = field(default_factory=list)


def apply(pages, placement: Placement, heads: HeadCandidates | None = None,
          *, head_region: int = HEAD_REGION, skip: Iterable[int] = ()) -> Applied:
    """Write the placement onto the pages: mark, join, and drop what fell.

    Three things happen to a page in one pass over its lines, because they
    all move the same indices: a placed entry's line gets the mark and the
    lines that spell the rest of its title out; a head candidate the
    placement did not confirm is removed, the folio it carried having been
    rescued long before; everything else stays exactly as it stood.

    The line is found by its words, not by the index the search noted. Those
    indices are the raw channel's, and between it and the page body lie the
    strippers, the folio candidates and the cut apparatus. What the two
    channels do share is the wording and which side of the head region it
    stands on, and that is enough to say which occurrence is meant.
    """
    result = Applied()
    by_pos = placement.by_position()
    # Rule 6 speaks of every *further* occurrence of a title in a head region.
    # A wording that was never placed at all has no first occurrence to be
    # further than, and removing it would take a line the volume prints out of
    # the volume on no evidence but a guess about where its heading is.
    placed_titles = {fold(p.want.title) for p in placement.placed}
    skipped = set(skip)
    for page in pages:
        body = page.body_lines
        here = by_pos.get(page.index, [])
        # The search never looked at the contents' own pages, where every
        # title stands, so it has no verdict about the lines there -- and a
        # judgement nobody made may not remove anything. The heading the
        # volume prints over its list is one of those lines.
        cands = ([] if page.index in skipped or heads is None
                 else heads.at(page.index - 1))
        if not here and not cands:
            continue
        filled = [i for i, line in enumerate(body) if line.strip()]
        folded = [fold(body[i]) for i in filled]

        targets: dict[int, tuple[Placed, int]] = {}
        for placed in sorted(here, key=lambda p: p.line):
            found = _locate(folded, placed, head_region, taken=set(targets))
            if found is None:
                result.lost.append(placed)
                continue
            targets[found[0]] = (placed, found[1])

        on_line = [(_candidate_line(folded, c, head_region), c) for c in cands]
        drop = {k for k, c in on_line
                if k is not None and k not in targets
                and (c.from_stripper or fold(c.title) in placed_titles)}
        result.heads_removed += len(drop)
        result.heads_kept += sum(1 for k, _c in on_line
                                 if k is not None and k in targets)

        at = {i: k for k, i in enumerate(filled)}
        out: list[str] = []
        consumed: set[int] = set()
        for i, line in enumerate(body):
            if i in consumed:
                continue
            if not line.strip():
                out.append(line)
                continue
            k = at[i]
            if k in drop:
                continue
            if k not in targets:
                out.append(line)
                continue
            placed, n_lines = targets[k]
            take = filled[k: k + n_lines]
            consumed.update(range(take[0] + 1, take[-1] + 1))
            out.append(mark_placed(" ".join(body[j].strip() for j in take),
                                   placed.want.depth))
            result.marked += 1
            result.joined += n_lines > 1
        page.body_lines = out
        if targets and not page.heading:
            # For assign_modes, assign_regions and the contents search, which
            # read a page's heading and know nothing of marks. It is not
            # rendered a second time: the line itself carries it now.
            page.heading = targets[min(targets)][0].want.text
            page.heading_in_body = True
    return result


def _locate(folded: list[str], placed: Placed, head_region: int,
            taken: set[int]) -> tuple[int, int] | None:
    """(line, how many lines) of this placement in the page's body."""
    spans = [s for s in folded_spans(folded, fold(placed.want.title), opens=True)
             if s[0] not in taken]
    side = [s for s in spans if (s[0] < head_region) == placed.in_head]
    if side:
        return side[min(placed.rank, len(side) - 1)]
    return spans[0] if spans else None


def _candidate_line(folded: list[str], candidate, head_region: int) -> int | None:
    """Which body line this head candidate is, or None where it is gone."""
    want = fold(candidate.text)
    if not want:
        return None
    for k in range(min(head_region, len(folded))):
        if similar(folded[k], want):
            return k
    return None


# ── the positive list, and the level below the list (§5.4) ─────────────

# What a line may not end in and still be a heading: the printer's marks for
# "this goes on". Measured in G6, where they separate the seven real lowest
# levels from the enumerations and note blocks around them.
_RUNS_ON = re.compile(r"[-–—,;:]$")

# How much shorter than its page's own lines a heading is (G6).
SHORT_LINE = 0.75

# A sentence that has ended. A line standing under one that has not is its
# continuation, whatever it is numbered.
_SENTENCE_END = re.compile(r"[.!?][\"'»«“”’)\]]*$")


def placed_schemes(placement: Placement, *, roman: bool) -> set[str]:
    """The numbering schemes the volume's list actually placed a heading in.

    The positive list refuses a numbered line because the list *leads* that
    level and names no entry here. That argument holds only where the list
    demonstrably works for the level: a contents the parser read badly, or one
    the volume prints without page numbers, leads every level and places
    nothing, and refusing on its word would take the headings away twice over.
    Measured on the sixty-one blind runs of G2 (c), where the contents is
    often all there is -- and where a list of six entries refused forty lines.
    A list has to have placed ``MIN_PLACED_TO_REFUSE`` headings before it
    speaks for the volume at all.
    """
    if len(placement.placed) < MIN_PLACED_TO_REFUSE:
        return set()
    return {scheme_of(p.want.text, roman)[0] for p in placement.placed} - {""}


def judge_numbering(pages, table: SchemeTable, *, roman: bool,
                    leads: set[str] | None = None) -> Applied:
    """The numbered lines no entry placed: refuse them, or take the level the
    list never wrote down (Gliederungsmodell §5.4).

    Two rules, and they are each other's opposite. A line numbered in a
    scheme the volume's own list *uses* is not a heading where no entry of
    that list stands: Bauer's eleven theses are numbered "1." to "11." like
    every section of the fourth level, and the contents names none of them.
    A line numbered in a scheme the list does *not* use is the level beneath
    the whole list -- "aa)" under "a)" -- but only where it stands in a run
    with its siblings, is short for its page, and continues no sentence.
    Without those three G6 found nineteen volumes' worth of footnotes,
    enumerations and one map legend.

    A line the typesetter set apart is left to both: type is a witness of its
    own (§5.1), and text may not overrule it here.

    ``leads`` are the schemes the list actually placed a heading in
    (``placed_schemes``); only those may refuse. Without it every scheme of
    the table refuses, which is right where the contents was read well and
    wrong everywhere else.
    """
    result = Applied()
    if not table.rows:
        return result
    deepest = max(r.depth for r in table.rows)
    runs: dict[str, list[tuple]] = {}
    keep: list[tuple] = []

    def flush() -> None:
        for run in runs.values():
            ordinals = [c[3] for c in run]
            # In sequence, and G6 means it: a), b), c) and 1., 2., 3. -- every
            # step of one. Merely ascending admits a run of numbered
            # quotations (15., 20., 23., 28. in Artificial Humanities), which
            # counts but does not divide.
            if len(run) >= 2 and all(b - a == 1 for a, b in zip(ordinals, ordinals[1:])):
                keep.extend(run)
        runs.clear()

    for page in pages:
        if page.mode != "main":
            continue
        widths = [len(line) for line in page.body_lines if line.strip()]
        width = median(widths) if widths else 0
        previous = ""
        for i, line in enumerate(page.body_lines):
            if not line.strip():
                previous = ""
                continue
            text, marked, depth = read_mark(line)
            if depth is not None:
                flush()             # a heading of any depth ends a run
            elif marked:
                pass                # the type has spoken; text does not argue
            else:
                scheme, designator, _title = scheme_of(text, roman)
                if (scheme and table.depth_of(scheme) is not None
                        and (leads is None or scheme in leads)):
                    if _reads_as_heading(text):
                        page.body_lines[i] = mark_placed(text, 0)
                        result.refused.append({"page": page.label, "text": text,
                                               "reason": "not-in-contents"})
                elif (scheme and table.depth_of(scheme) is None
                        and _short(text, width) and (
                        not previous or _SENTENCE_END.search(previous.strip()))):
                    ordinal = _ordinal(designator)
                    if ordinal is not None:
                        runs.setdefault(scheme, []).append((page, i, text, ordinal))
            previous = text
        # A page break ends no run: La masonería sets seventeen of these in a
        # row over thirty-one pages (G6). Only a heading does.
    flush()

    for page, i, text, _ordinal_value in keep:
        page.body_lines[i] = mark_placed(text, deepest + 1)
        result.promoted.append({"page": page.label, "text": text,
                                "depth": deepest + 1})
    return result


def _short(text: str, width: float) -> bool:
    """Short for the page it stands on, and not broken off at its end."""
    return bool(width) and len(text) <= width * SHORT_LINE and not _RUNS_ON.search(
        text.strip())


def _reads_as_heading(text: str) -> bool:
    """Would the text alone have made this line a heading?"""
    from scriptor.reflow.core import heading_level

    return heading_level(text) > 0


_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _ordinal(designator: str) -> int | None:
    """What place in its series this designator states: a) -> 1, bb) -> 2.

    A series is what the lowest level has instead of an entry: the volume
    never wrote it down, so the only thing saying these lines belong together
    is that they count.
    """
    token = designator.strip().strip("()[]").rstrip(".):-– ").lstrip("(")
    if not token:
        return None
    if token.isdigit():
        return int(token)
    low = token.lower()
    if low.isalpha() and low.isascii() and len(set(low)) == 1:
        return ord(low[0]) - ord("a") + 1          # a), aa), bbb)
    if low.isascii() and all(c in _ROMAN_VALUES for c in low):
        total, highest = 0, 0
        for value in (_ROMAN_VALUES[c] for c in reversed(low)):
            total += value if value >= highest else -value
            highest = max(highest, value)
        return total
    return None
