"""Heading metric: does the output carry the division the volume prints?

Ground truth declares every heading with its page, its depth in the volume's
own tree, the printed designator and the title (``TruthHeading``). Measured
against the ``#`` lines of a prepared document, kept apart and not averaged,
because the failures do not cost the same (Gliederungsmodell §3.6):

* **placement** -- recall: does each heading stand as a ``#`` line on its
  page? precision: does each ``#`` line stand in the truth? Keyed by page
  label and title, folded as ``outline._norm`` folds and compared at its
  ratio. A heading cut off at the end of its printed line still stands where
  it belongs; it counts as placed and is marked ``truncated``. So does a line
  that carries the whole title and runs on past it.
* **depth** -- exact per placed heading, and the *steps*: wherever the truth
  turns deeper or shallower from one placed heading to the next, does the
  output turn the same way? A systematic offset keeps every step; flattening
  the tree loses them. Steps between siblings are not counted -- most
  neighbours are siblings, and a flat output would keep them all.
* **chapter depth** -- the depth on which the output sets the headings the
  truth puts on its chapter level, against that level.
* **deleted titles** -- a title found nowhere on its page. The silent defect:
  the words are gone and nothing says so. A list, not a rate, like false
  apparatus in the region metric. That the title survives in the rebuilt
  contents list does not count -- the contents region is not searched.
* **running heads in the text** -- a heading's printed wording, designator
  and title, glued into the reading flow at a page seam, where a running
  head the stripper missed lands (Bauer p. 23, §2.1). What tells it from the
  heading itself, glued to its paragraph at the top of its page: a running
  head *interrupts* a sentence that runs on across the page; a heading
  follows a finished one. Where the page broke between paragraphs, only the
  page can tell: an occurrence on a page no heading of that wording stands on.
  A head line carries a second witness -- the printed designator, or the
  folio beside the words; a bare title without either is too often a phrase
  of the prose ("durch natürliche [p. 774] Auslese") and is not counted.
* **false headings** -- ``#`` lines the truth does not know, with their text.

A heading that opens a page stands before that page's marker (spec 0.4.0
§4.2), so its page is the marker's of the block that follows it.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from scriptor.document import FLAG_RE
from scriptor.eval.adapters import ANCHOR_RE, ParsedDoc, page_at
from scriptor.eval.ground_truth import GroundTruth, TruthHeading
from scriptor.reflow.outline import MATCH_RATIO

HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(\S[^\n]*?)[ \t]*$", re.MULTILINE)
# The block after a heading run opens with the page marker the run belongs to.
_OPENS_PAGE_RE = re.compile(r"\s*(?:#{1,6}[ \t][^\n]*\n\s*)*\[p\. ([^\]]+)\]")
_MARKER_RE = re.compile(r"\[p\. ([^\]]+)\](?:\{#[^}]*\})?")
_NOISE_RES = (ANCHOR_RE, FLAG_RE, re.compile(r"\{\.cit[^}]*\}"))
# What may stand between a sentence and what follows it without ending it.
_TAIL_RE = re.compile(r"(?:\s|\[\^\d+\]|\[p\. [^\]]+\](?:\{#[^}]*\})?)+$")
_SENTENCE_END = ".!?"
_WORD_RE = re.compile(r"[^\W\d_]{2,}")
# A sentence closed and then given its note number the converter left as digits.
_NOTE_AFTER_END = re.compile(r"[.!?][\"'»«“”’)\]]*\d{1,3}$")
# How near the words a folio may stand to count as the rest of their head line.
_FOLIO_REACH = 12
_CLOSERS = "\"'»«“”’)]"
# How far past a seam a running head may begin: the digits of a folio.
_SEAM_SLACK = 3
# A cut heading must still carry half its title before it counts as placed.
_MIN_PREFIX = 8
# Below this a wording is too short to tell a running head from prose: the
# letter heads of an index stand next to every page marker somewhere.
_MIN_WORDING = 5


@dataclass
class OutputHeading:
    """A ``#`` line of the output."""
    page: str
    depth: int
    text: str


@dataclass
class PlacedHeading:
    truth: TruthHeading
    page: str
    depth: int
    text: str
    truncated: bool = False


@dataclass
class HeadingResult:
    total: int = 0
    placed: list[PlacedHeading] = field(default_factory=list)
    missed: list[TruthHeading] = field(default_factory=list)
    output_total: int = 0
    false_headings: list[OutputHeading] = field(default_factory=list)
    depth_exact: int = 0
    steps_total: int = 0
    steps_kept: int = 0
    chapter_level: int | None = None
    chapter_depth_found: int | None = None
    deleted: list[TruthHeading] = field(default_factory=list)
    running_in_text: list[tuple[TruthHeading, str]] = field(default_factory=list)

    @property
    def placed_count(self) -> int:
        return len(self.placed)

    @property
    def recall(self) -> float:
        return self.placed_count / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        return self.placed_count / self.output_total if self.output_total else 0.0


def evaluate_headings(truth: GroundTruth, doc: ParsedDoc) -> HeadingResult:
    if not truth.headings:
        return HeadingResult()

    spans = _heading_spans(doc)
    output = [h for _, _, h in spans]
    result = HeadingResult(total=len(truth.headings), output_total=len(output),
                           chapter_level=truth.chapter_level)

    matched = _match(truth.headings, output)
    for i, head in enumerate(truth.headings):
        if i in matched:
            j, truncated = matched[i]
            out = output[j]
            result.placed.append(PlacedHeading(head, out.page, out.depth, out.text,
                                               truncated))
        else:
            result.missed.append(head)
    used = {j for j, _ in matched.values()}
    result.false_headings = [h for j, h in enumerate(output) if j not in used]

    _measure_depth(result)
    _search_titles(truth.headings, set(matched), doc, spans, result)
    return result


# the output's headings -----------------------------------------------------

def _heading_spans(doc: ParsedDoc) -> list[tuple[int, int, OutputHeading]]:
    spans = []
    for m in HEADING_LINE_RE.finditer(doc.body):
        opens = _OPENS_PAGE_RE.match(doc.body, m.end())
        page = opens.group(1) if opens else page_at(doc, m.start())
        spans.append((m.start(), m.end(),
                      OutputHeading(page, len(m.group(1)), m.group(2))))
    return spans


def _fold(text: str) -> str:
    """Letters and digits, case-folded -- ``outline._norm``, one character at a
    time, so that folding the body can keep where each character came from."""
    return "".join(lc for c in text for lc in c.lower() if lc.isalnum())


def _match(heads: list[TruthHeading],
           output: list[OutputHeading]) -> dict[int, tuple[int, bool]]:
    """Truth index -> (output index, truncated). One to one, best pairs first,
    so that a near-miss title cannot take the line its neighbour prints."""
    by_page: dict[str, list[int]] = {}
    for j, out in enumerate(output):
        by_page.setdefault(out.page, []).append(j)
    folded = [_fold(out.text) for out in output]

    pairs = []
    for i, head in enumerate(heads):
        full, title = _fold(f"{head.designator} {head.title}"), _fold(head.title)
        for j in by_page.get(head.page, []):
            got = folded[j]
            ratio = max(SequenceMatcher(None, got, full).ratio(),
                        SequenceMatcher(None, got, title).ratio())
            if ratio >= MATCH_RATIO or any(
                    len(t) >= max(_MIN_PREFIX, len(got) // 2) and got.startswith(t)
                    for t in (full, title)):
                # The line carries the whole title, and perhaps more: outlines
                # cut long titles, and a heading may run into its paragraph.
                pairs.append((ratio, i, j, False))
            elif any(len(got) >= max(_MIN_PREFIX, len(t) // 2) and t.startswith(got)
                     for t in (full, title)):
                pairs.append((ratio, i, j, True))

    matched: dict[int, tuple[int, bool]] = {}
    taken: set[int] = set()
    for _ratio, i, j, truncated in sorted(pairs, key=lambda p: (-p[0], p[1], p[2])):
        if i not in matched and j not in taken:
            matched[i] = (j, truncated)
            taken.add(j)
    return matched


def _measure_depth(result: HeadingResult) -> None:
    result.depth_exact = sum(1 for p in result.placed if p.depth == p.truth.depth)
    for a, b in zip(result.placed, result.placed[1:]):
        turn = _sign(b.truth.depth - a.truth.depth)
        if turn:
            result.steps_total += 1
            result.steps_kept += turn == _sign(b.depth - a.depth)
    chapters = Counter(p.depth for p in result.placed
                       if p.truth.depth == result.chapter_level)
    if chapters:
        top = max(chapters.values())
        result.chapter_depth_found = min(d for d, n in chapters.items() if n == top)


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


# titles in the text ----------------------------------------------------------

@dataclass
class _Folded:
    text: str                       # the body outside contents, folded
    origin: list[int]               # body offset of each folded character
    seams: list[int]                # folded position of each page marker
    seam_labels: list[str]


def _fold_body(doc: ParsedDoc) -> _Folded:
    body = doc.body
    skips = [(m.start(), m.end(), m.group(1)) for m in _MARKER_RE.finditer(body)]
    for rx in _NOISE_RES:
        skips += [(m.start(), m.end(), None) for m in rx.finditer(body)]
    skips += [(s, e, None) for s, e in _contents_spans(doc)]
    skips.sort()

    chars: list[str] = []
    origin: list[int] = []
    seams: list[int] = []
    labels: list[str] = []
    pos = 0
    for start, end, label in skips + [(len(body), len(body), None)]:
        for i in range(pos, max(pos, start)):
            for lc in body[i].lower():
                if lc.isalnum():
                    chars.append(lc)
                    origin.append(i)
        if label is not None and start >= pos:
            seams.append(len(chars))
            labels.append(label)
        pos = max(pos, end)
    return _Folded("".join(chars), origin, seams, labels)


def _contents_spans(doc: ParsedDoc) -> list[tuple[int, int]]:
    marks = doc.region_marks
    return [(off, marks[k + 1][1] if k + 1 < len(marks) else len(doc.body))
            for k, (name, off) in enumerate(marks) if name == "contents"]


@dataclass
class _Occurrence:
    offset: int                     # in the body
    end: int
    page: str
    in_heading: bool
    at_seam: bool


def _occurrences(needle: str, lead: int, folded: _Folded, doc: ParsedDoc,
                 spans: list[tuple[int, int, OutputHeading]]) -> list[_Occurrence]:
    """Every place the folded needle stands, with the page it stands on.

    `lead` is how many folded characters may precede it at a seam and still
    belong to it: a designator's, when the needle is a bare title.
    """
    starts = [s for s, _, _ in spans]
    found = []
    k = folded.text.find(needle)
    while needle and k >= 0:
        end = k + len(needle)
        offset, stop = folded.origin[k], folded.origin[end - 1] + 1
        h = bisect_right(starts, offset) - 1
        if h >= 0 and offset < spans[h][1]:
            found.append(_Occurrence(offset, stop, spans[h][2].page, True, False))
        else:
            # A seam inside the needle, or just before it -- where a folio of
            # a running head would stand.
            s = bisect_right(folded.seams, k - lead - _SEAM_SLACK - 1)
            if s < len(folded.seams) and folded.seams[s] < end:
                found.append(_Occurrence(offset, stop, folded.seam_labels[s], False, True))
            else:
                found.append(_Occurrence(offset, stop, page_at(doc, offset), False, False))
        k = folded.text.find(needle, k + 1)
    return found


def _beside_folio(body: str, start: int, end: int, label: str) -> bool:
    """Does the page's printed number stand right by the words -- the other
    half of a head line? Markers and note anchors in between are read through."""
    number = re.compile(rf"(?<!\w){re.escape(label)}(?!\w)", re.IGNORECASE)
    before = ANCHOR_RE.sub(" ", _MARKER_RE.sub(" ", body[max(0, start - 60):start]))
    after = ANCHOR_RE.sub(" ", _MARKER_RE.sub(" ", body[end:end + 60]))
    return bool(number.search(before.rstrip()[-_FOLIO_REACH:])
                or number.search(after.lstrip()[:_FOLIO_REACH]))


def _interrupts_sentence(body: str, offset: int) -> bool:
    """Does the text at `offset` break into a sentence still running?

    Not where it opens a paragraph, nor after a finished sentence; footnote
    anchors and page markers in between are read through. A paragraph that
    holds no words before it -- a stray folio digit -- holds no sentence.
    """
    before = body[body.rfind("\n\n", 0, offset) + 1:offset]
    tail = _TAIL_RE.search(before)
    if tail:
        before = before[:tail.start()]
    if len(_WORD_RE.findall(before)) < 2 or _NOTE_AFTER_END.search(before):
        return False
    last = before[-1]
    if last in _CLOSERS and len(before) > 1:
        last = before[-2]
    return last not in _SENTENCE_END


def _search_titles(heads: list[TruthHeading], placed: set[int], doc: ParsedDoc,
                   spans: list[tuple[int, int, OutputHeading]],
                   result: HeadingResult) -> None:
    folded = _fold_body(doc)
    marked = {label for label, _ in doc.page_marks}
    for i, head in enumerate(heads):
        if i in placed:
            # Its line stands on its page -- in the contents region, too,
            # which the search below leaves out.
            continue
        found = _occurrences(_fold(head.title), len(_fold(head.designator)),
                             folded, doc, spans)
        own = [o for o in found if o.page == head.page]
        if not (own if head.page in marked else found):
            result.deleted.append(head)

    # A running head prints the heading's wording, designator included; the
    # title alone is too often a phrase of the prose. Headings sharing one
    # wording share their pages: an occurrence on any of them may be the heading.
    wordings: dict[str, list[TruthHeading]] = {}
    for head in heads:
        wordings.setdefault(_fold(f"{head.designator} {head.title}"), []).append(head)
    for needle, same in wordings.items():
        if len(needle) < _MIN_WORDING:
            continue
        pages = {h.page for h in same}
        designated = any(h.designator for h in same)
        for o in _occurrences(needle, 0, folded, doc, spans):
            if not o.at_seam:
                continue
            if not (_interrupts_sentence(doc.body, o.offset) or o.page not in pages):
                continue
            if designated or _beside_folio(doc.body, o.offset, o.end, o.page):
                result.running_in_text.append((same[0], o.page))
