"""``scriptor headings``: the division written into a finished master.

The reflow places a volume's headings while it still has the pages in front of
it -- the head region, the folios, the type. A master that has since been
*edited* cannot be produced again: rebuilding it would throw the edits away.
So this is the second entrance (Gliederungsmodell §4.5): the same rules,
reading the same evidence, but out of the finished document.

What is left of that evidence in a master is the volume's own contents list,
rendered as a link list in the ``contents`` region, and the text. The
indentation of the list states the depth (the reflow learnt it there); the
wording of an entry is searched for in the text; where it is found, a ``#``
line is written -- and nothing else is written. The structure sidecar (§6.5)
is written beside the master, as a reflow run writes it.

This is the user's tool. ``scriptor_prepare.py`` never calls it: inserting a
heading is an insertion into someone's edited text, and that is a decision,
not a step of a pipeline. It is idempotent, so calling it twice costs nothing.

Not ``scriptor.reflow.headings``, which is the typographic mark inside the
reflow -- a different thing at a different stage.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scriptor.document import REGION_LINE_RE, structure_of_master
from scriptor.reflow import placement as placement_mod
from scriptor.reflow.headings import read_mark
from scriptor.reflow.outline import fold
from scriptor.reflow.pagelabel import PAGE_MARKER_RE
from scriptor.reflow.regions import read_metadata_block, region_of_heading
from scriptor.structure import (
    MAX_MARKDOWN_DEPTH,
    Witness,
    describe,
    is_roman_volume,
    scheme_of,
    table_from,
)

# An entry of the rendered contents list (reflow/toc.render_toc): a bullet,
# indented two spaces per level, the title either linked to its page anchor or
# bare, and the printed page after an em dash where the list names one.
_ENTRY_RE = re.compile(
    r"^(?P<indent>[ \t]*)-[ \t]+"
    r"(?:\[(?P<linked>[^\]]+)\]\([^)]*\)|(?P<plain>.+?))"
    r"(?:[ \t]+—[ \t]+p\.[ \t]*(?P<page>\S+))?[ \t]*$"
)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*)$")
# A page marker, anchored or not, at the head of a piece of text.
_OPENING_MARKER_RE = re.compile(r"^(\[p\. [^\]]+\](?:\{#[^}]*\})?)[ \t]*")
# Lines that are declaration or apparatus rather than the volume's text: a
# region marker (§4.4) and a footnote definition (§4.3). No heading goes in.
_DECLARATION_RE = re.compile(r"^\[region:\s*[a-z-]+\]\s*$|^\[\^\d+\]:")


@dataclass
class Report:
    placed: int = 0
    promoted: int = 0
    unplaced: int = 0
    rejected: int = 0
    existing: int = 0        # '#' lines the master already carried
    entries: int = 0
    changed: bool = False


# ── reading the master ────────────────────────────────────────────────

def _split_block(text: str) -> tuple[str, str]:
    """(metadata block including its blank line, the rest)."""
    m = re.match(r"\A---\n.*?\n---\n+", text, re.DOTALL)
    return (m.group(0), text[m.end():]) if m else ("", text)


def _contents_spans(body: str) -> list[tuple[int, int]]:
    """Every ``contents`` region of ``body``, in reading order.

    A volume lists more than its chapters: Bauer follows its contents with a
    list of figures, and that is a ``contents`` region too. The entries are
    read from the first (§5.2: the placement hears the volume's own list, not
    every list behind it), and all of them are kept out of the text the
    placement searches -- every title stands in a list.
    """
    spans: list[tuple[int, int]] = []
    marks = [(m.group(1), m.start(), m.end()) for m in REGION_LINE_RE.finditer(body)]
    for i, (name, _start, end) in enumerate(marks):
        if name == "contents":
            spans.append((end, marks[i + 1][1] if i + 1 < len(marks) else len(body)))
    return spans


@dataclass(frozen=True)
class _Entry:
    text: str
    page: str | None
    depth: int


def _entries(listing: str) -> list[_Entry]:
    """The list's entries, in reading order. The indentation is the depth:
    ``render_toc`` writes two spaces per level and the reflow learnt those
    levels from the printed list (Gliederungsmodell §5.1)."""
    out: list[_Entry] = []
    for line in listing.splitlines():
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        title = (m.group("linked") or m.group("plain") or "").strip()
        if not title:
            continue
        out.append(_Entry(text=title, page=m.group("page"),
                          depth=len(m.group("indent").expandtabs(2)) // 2 + 1))
    return out


# ── the channel the placement reads ───────────────────────────────────

def _fold_with_offsets(s: str) -> tuple[str, list[int]]:
    """``fold(s)`` and, per folded character, where it came from."""
    out, idx = [], []
    for i, ch in enumerate(s):
        lc = ch.lower()
        if lc.isalnum():
            out.append(lc)
            idx.append(i)
    return "".join(out), idx


@dataclass
class _Piece:
    """One line of the channel the placement searches, and where it stands."""
    start: int              # offset into the body
    text: str


def _pieces(body: str, skip: list[tuple[int, int]]) -> list[_Piece]:
    """The body as lines: the text a heading may be written into, and no more.

    A master's paragraph is one long line, so a title the reflow never found
    stands inside one rather than on top of one. The cuts that make it
    findable come next (``_cut_at_titles``); here the text is only broken
    where it already breaks, and in front of every page marker, so that a
    heading opening a page can be told from one standing inside it.

    Left out: the contents regions, where every title stands; the region
    markers, which are declaration and not text (a volume whose contents names
    a chapter "Notes" had ``# notes`` written into ``[region: notes]``); and
    the footnote definitions, where a title is quoted, not printed.
    """
    pieces: list[_Piece] = []
    for m in re.finditer(r"[^\n]*", body):
        if m.start() == m.end() and m.start() != len(body):
            continue
        if any(a <= m.start() < b for a, b in skip) or _DECLARATION_RE.match(m.group(0)):
            continue
        at = m.start()
        line = m.group(0)
        cuts = sorted({0} | {k.start() for k in PAGE_MARKER_RE.finditer(line) if k.start()})
        for a, b in zip(cuts, cuts[1:] + [len(line)]):
            pieces.append(_Piece(at + a, line[a:b]))
    return pieces


def _cut_at_titles(pieces: list[_Piece], titles: list[str]) -> list[_Piece]:
    """Break every piece at both ends of an entry's wording inside it.

    The placement asks whether a *line* is the title it is looking for; in a
    master the title is glued to the prose that follows it and to the page
    marker in front of it, so the line has to be made first. Only a wording
    the list names cuts anything -- nothing else in the text is moved, and a
    cut that finds no title leaves its piece whole.
    """
    needles = [fold(t) for t in titles if len(fold(t)) >= placement_mod.MIN_TITLE]
    out: list[_Piece] = []
    for piece in pieces:
        if _HEADING_RE.match(piece.text):
            # Already a heading, and a whole line. Cutting the hashes off it
            # would make the second run write them again.
            out.append(piece)
            continue
        folded, idx = _fold_with_offsets(piece.text)
        cuts = {0}
        for needle in needles:
            at = folded.find(needle)
            while at >= 0:
                cut = idx[at]
                # Back over the punctuation the fold dropped: "(1)" opens at
                # the bracket, not at the digit.
                while cut and not piece.text[cut - 1].isspace() \
                        and not piece.text[cut - 1].isalnum():
                    cut -= 1
                if cut == 0 or piece.text[cut - 1].isspace():
                    cuts.add(cut)
                    cuts.add(idx[at + len(needle) - 1] + 1)
                at = folded.find(needle, at + 1)
        ordered = sorted(c for c in cuts if c <= len(piece.text))
        for a, b in zip(ordered, ordered[1:] + [len(piece.text)]):
            if b > a:
                out.append(_Piece(piece.start + a, piece.text[a:b]))
    return out


def _paginate(pieces: list[_Piece]) -> tuple[dict[int, list[str]], dict[int, tuple[str, str]],
                                             dict[tuple[int, int], _Piece]]:
    """The channel keyed the way ``placement.place`` wants it.

    A piece opening with a page marker opens that page, so a heading written
    in front of the marker and one written behind it land on the same page --
    which is what spec §4.2 says they mean.
    """
    raw: dict[int, list[str]] = {0: []}
    labels: dict[int, tuple[str, str]] = {}
    where: dict[tuple[int, int], _Piece] = {}
    pos = 0
    held: list[_Piece] = []

    def emit(piece: _Piece, at: int) -> None:
        raw.setdefault(at, [])
        where[(at, len(raw[at]))] = piece
        raw[at].append(piece.text)

    for piece in pieces:
        m = _OPENING_MARKER_RE.match(piece.text)
        if m:
            pos += 1
            labels[pos] = (PAGE_MARKER_RE.match(piece.text).group(1), "printed")
            raw.setdefault(pos, [])
        elif _HEADING_RE.match(piece.text):
            # A heading standing in front of a marker opens that page (§4.2),
            # so it waits to see whether one follows. Without this a second run
            # does not find the heading the first one wrote on the page it
            # belongs to, and places the entry somewhere else instead.
            held.append(piece)
            continue
        for piece_held in held:
            emit(piece_held, pos)
        held = []
        emit(piece, pos)
    for piece_held in held:
        emit(piece_held, pos)
    return raw, labels, where


# ── writing the headings in ───────────────────────────────────────────

@dataclass(frozen=True)
class _Write:
    start: int          # where the heading's first character stands
    end: int            # where it ends
    depth: int


# Below this many folded characters a tail is too short to say that the piece
# after a break carries the rest of a title rather than opening a sentence.
_MIN_TAIL = 4
# How much more than its wording a heading's run may cover before it is no
# heading but a stretch of the text the pieces happen to be adjacent in.
_SPAN_SLACK = 40


# What may stand in front of a heading: the end of a sentence, of a marker, or
# of a line. A word may not -- print sets a heading on a line of its own, and a
# wording found inside a sentence is the volume using its own words again.
_BEFORE_A_HEADING = set(".!?:;»”’\"')]}–—*_")


def _stands_alone(body: str, start: int) -> bool:
    """Does a heading written at ``start`` begin where a line could begin?

    The one guard the master cannot take from the print. A volume whose
    chapters are called "Samuel", "Saul", "David" names them again in every
    other sentence, and on the right page the placement has nothing to tell
    the heading from the prose: the head region it uses for that is gone.
    """
    k = start - 1
    while k >= 0 and body[k] in " \t":
        k -= 1
    return k < 0 or body[k] == "\n" or body[k] in _BEFORE_A_HEADING


def _at(where: dict, pos: int) -> dict[int, _Piece]:
    """The pieces of one page, by their line number."""
    return {line: piece for (p, line), piece in where.items() if p == pos}


def _span_of(body: str, at: dict[int, _Piece], placed, title: str) -> tuple[int, int] | None:
    """Where the heading stands in the body, in the body's own offsets.

    The placement answers with a *run* of pieces, and the run is the heading:
    the cut leaves a designator standing alone whenever the list prints its
    entries without one ("I." / "Iconic turn und die digitale Bilderflut"),
    and taking only the first piece would write the designator and leave the
    title in the prose. A page marker at the head of the run belongs to the
    page, not to the heading, and stays behind. And where the title broke
    across a paragraph -- the master keeps the break the print made (§8.5) --
    the piece after the run opens with the rest of the wording, and the
    heading reaches to where that ends: only that far, only where the tail is
    long enough to be a title's and not a sentence's.
    """
    first = at.get(placed.line)
    last = at.get(placed.line + placed.n_lines - 1, first)
    if first is None or last is None:
        return None
    start, text = first.start, first.text
    m = _OPENING_MARKER_RE.match(text)
    if m:
        start, text = start + m.end(), text[m.end():]
    end = last.start + len(last.text.rstrip())
    if end <= start or end - start > len(title) * 2 + _SPAN_SLACK:
        return None
    needle = fold(title)
    after = at.get(placed.line + placed.n_lines)
    if after is None or not needle or fold(body[start:end]).endswith(needle[-_MIN_TAIL:]):
        return start, end
    folded, idx = _fold_with_offsets(after.text)
    for k in range(min(len(needle), len(folded)), _MIN_TAIL - 1, -1):
        if folded.startswith(needle[-k:]):
            return start, after.start + idx[k - 1] + 1
    return start, end


def _apply(body: str, writes: list[_Write]) -> str:
    """The body with a ``#`` line written at each place, and nothing else.

    A heading is a line, so the text around it is broken where it has to be
    and nowhere else. Where the heading opens a page, the page marker moves
    behind it: spec §4.2 has a page's first heading standing in front of the
    marker, which is how every consumer reads which page it is on.
    """
    out: list[str] = []
    at = 0
    for w in sorted(writes, key=lambda w: w.start):
        if w.start < at:
            continue
        before = body[at:w.start]
        head, sep, tail = before.rpartition("\n\n")
        marker = ""
        if tail and _OPENING_MARKER_RE.fullmatch(tail):
            # Nothing stands between the marker and the heading, so the
            # heading opens that page: it goes in front of the marker.
            marker = _OPENING_MARKER_RE.fullmatch(tail).group(1) + " "
            before = head + sep
        hashes = "#" * min(w.depth, MAX_MARKDOWN_DEPTH)
        # A title that broke across a paragraph becomes one line again: that
        # is the break the print made, and a heading is a line.
        title = " ".join(body[w.start:w.end].split())
        out.append(before.rstrip(" \t"))
        out.append(f"\n\n{hashes} {title}\n\n{marker}")
        at = w.end
        while at < len(body) and body[at] in " \t":
            at += 1
    out.append(body[at:])
    return re.sub(r"\n{3,}", "\n\n", "".join(out))


# ── the whole of it ───────────────────────────────────────────────────

def mark_headings(text: str):
    """(the master with its headings, the Structure, a Report).

    A master with no contents list to read is returned untouched: there is
    nothing here that guesses a division out of the prose.
    """
    metadata = read_metadata_block(text)
    if not metadata or not metadata.get("format_version"):
        raise ValueError("not a prepared document: the metadata block names no format_version")

    block, body = _split_block(text)
    spans = _contents_spans(body)
    entries = _entries(body[spans[0][0]:spans[0][1]]) if spans else []
    report = Report(entries=len(entries))
    if not entries:
        return text, None, report

    roman = is_roman_volume(e.text for e in entries)
    schemes = [scheme_of(e.text, roman)[0] for e in entries]
    table = table_from([e.depth for e in entries], schemes)
    wants = [placement_mod.Want(text=e.text, title=e.text, depth=e.depth,
                                page=e.page, source="contents",
                                region=region_of_heading(scheme_of(e.text, roman)[2]))
             for e in entries]

    pieces = _cut_at_titles(_pieces(body, spans), [e.text for e in entries])
    raw, labels, where = _paginate(pieces)
    placement = placement_mod.place(wants, raw, labels, head_region=0)

    writes: list[_Write] = []
    for p in placement.placed:
        piece = where.get((p.pos, p.line))
        if piece is None:
            continue
        if _HEADING_RE.match(piece.text):
            continue                    # already a heading; its depth is below
        found = _span_of(body, _at(where, p.pos), p, p.want.title)
        if found and _stands_alone(body, found[0]):
            writes.append(_Write(found[0], found[1], p.want.depth))
    report.placed = len(writes)
    # On the uncut channel: a line is short *for its page*, and the cuts above
    # fill the page with fragments of the length of a title.
    whole_raw, whole_labels, whole_where = _paginate(_pieces(body, spans))
    promoted = _promoted(whole_raw, whole_labels, whole_where, table, placement,
                         roman, {w.start for w in writes})
    report.promoted = len(promoted)
    writes += promoted
    out_body = _apply(body, writes)
    report.unplaced = len(placement.unplaced)
    report.rejected = len(placement.rejected)

    known = {fold(e.text): (e.depth, "contents") for e in entries}
    known.update({fold(body[w.start:w.end]): (w.depth, "numbering") for w in promoted})
    depths = _depths(out_body, known)
    report.existing = sum(1 for _d, _t, source in depths if source == "stale")
    structure = structure_of_master(
        block + out_body, [(d, t) for d, t, _s in depths], table,
        region_of=region_of_heading,
        witness_of=_witness_of({fold(t): s for _d, t, s in depths}),
        unplaced=[{"text": w.text, "page": w.page} for w in placement.unplaced],
        rejected=[{"text": w.text, "page": w.page, "reason": why}
                  for w, why in placement.rejected],
    )
    out = _redeclare(block, describe(structure)) + out_body
    report.changed = out != text
    return out, structure, report


@dataclass
class _Page:
    """What ``judge_numbering`` asks of a page, and no more."""
    label: str | None
    body_lines: list[str]
    mode: str = "main"


def _promoted(raw, labels, where, table, placement, roman: bool,
              taken: set[int]) -> list[_Write]:
    """The level the list never wrote down (Gliederungsmodell §5.4).

    A line numbered in a form the volume's own table does not know, standing
    in a run with its siblings, is the level beneath the whole list -- "aa)"
    under "a)". Out of a master it reaches only a line that already stands on
    its own: the cuts above follow the list's wording, and a form the list
    never names cuts nothing.
    """
    pages = [_Page(labels.get(pos, (None, ""))[0], list(lines))
             for pos, lines in sorted(raw.items())]
    placement_mod.judge_numbering(
        pages, table, roman=roman,
        leads=placement_mod.placed_schemes(placement, roman=roman))
    out: list[_Write] = []
    for page, (pos, _lines) in zip(pages, sorted(raw.items())):
        for i, line in enumerate(page.body_lines):
            _text, _marked, depth = read_mark(line)
            piece = where.get((pos, i))
            if not depth or piece is None or piece.start in taken:
                continue
            out.append(_Write(piece.start,
                              piece.start + len(piece.text.rstrip()), depth))
    return out


def _depths(body: str, known: dict[str, tuple[int, str]]) -> list[tuple[int, str, str]]:
    """(depth, text, witness source) for every ``#`` line of ``body``.

    A line the list names takes the depth the list indents it to. One nothing
    here names is the user's own -- a heading written or changed by hand --
    and keeps the depth its hashes print, marked ``stale``: it stands in the
    master, and nothing here claims to know where it belongs.
    """
    out: list[tuple[int, str, str]] = []
    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if not m:
            continue
        text = m.group(2).strip()
        found = known.get(fold(text))
        out.append((found[0], text, found[1]) if found
                   else (len(m.group(1)), text, "stale"))
    return out


_WHY = {
    "contents": "the volume's own list names it here",
    "numbering": "a form the volume's table does not know, in a run with its siblings",
    "stale": "a heading of the master that no list of this volume names",
}


def _witness_of(sources: dict[str, str]):
    def witness(node):
        source = sources.get(fold(node.text))
        return [Witness(source, _WHY[source])] if source in _WHY else []
    return witness


def _redeclare(block: str, line: str) -> str:
    """The metadata block with its ``structure:`` line brought up to date."""
    if not block:
        return block
    declaration = f"structure: {line}"
    if re.search(r"^structure: .*$", block, re.MULTILINE):
        return re.sub(r"^structure: .*$", lambda _m: declaration,
                      block, count=1, flags=re.MULTILINE)
    # In front of the block's closing fence, so the field joins the others.
    head, fence, tail = block.rpartition("---")
    return f"{head}{declaration}\n{fence}{tail}" if fence else block


def run(master_path: str | Path, *, dry_run: bool = False) -> Report:
    """Write the headings into ``master_path`` and the sidecar beside it."""
    from scriptor.structure import render_structure_sidecar

    master = Path(master_path)
    text = master.read_text(encoding="utf-8")
    out, structure, report = mark_headings(text)
    if structure is None:
        print(f"{master.name}: no contents list to read -- nothing written",
              file=sys.stderr)
        return report

    print(f"Headings written: {report.placed} of "
          f"{report.entries} contents entries "
          f"({report.unplaced} found nowhere in the text, "
          f"{report.rejected} declined); "
          f"{report.promoted} taken as the level below the list; "
          f"{report.existing} the master already carried",
          file=sys.stderr)
    if dry_run:
        print(f"Dry run: {master} left as it is", file=sys.stderr)
        return report
    if not report.changed:
        print(f"{master.name}: already current -- not rewritten", file=sys.stderr)
    else:
        master.write_text(out, encoding="utf-8")
        print(f"Written: {master}", file=sys.stderr)
    json_text, txt = render_structure_sidecar(structure, master.name)
    master.with_name(master.name + ".structure.json").write_text(json_text, encoding="utf-8")
    report_path = master.with_name(master.name + ".structure.txt")
    report_path.write_text(txt, encoding="utf-8")
    print(f"Structure: {describe(structure)} -> {report_path}", file=sys.stderr)
    return report
