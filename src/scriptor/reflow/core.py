"""
PDF text reflow for scanned books.

Input: a directory of OCR text files (one per page, sorted).
Output: a merged TXT file with:
  - reconstructed paragraphs
  - de-hyphenated words
  - footnotes indented at the end of the paragraph
  - page markers [p. NN] inline
  - footnote markers [NN] in the running text
"""

from __future__ import annotations
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from scriptor._text import plural
from scriptor.reflow.footnotes import (
    FOOTNOTE_RE,
    PLACED_MARKER_RE,
    SUPERSCRIPT_DIGITS,
    match_definition,
    split_small_type_block,
    substitute_markers,
)
from scriptor.reflow.pagelabel import PAGE_MARKER_RE, decode_label, detect_page_label

# --- Configuration ---
INDENT = "    "                # indent of footnotes at the end of the paragraph
# FOOTNOTE_RE, PLACED_MARKER_RE, SUPERSCRIPT_DIGITS and substitute_markers now
# live in footnotes.py; page-label detection lives in pagelabel.py (both above).


# A footnote's identity inside a paragraph: (which page it came from, number
# printed next to it there). The printed number alone will not do — numbering
# restarts on every page in many books, while a paragraph may span the break, so
# two different notes would both be "1". Keying on that number silently drops one
# of them (KONZEPT_scriptor_v2.md §5.8: do not hard-wire "page-local").
FnKey = tuple[int, int]


@dataclass
class Page:
    num: int                              # ordinal value of the label (-1 = none)
    body_lines: list[str]                 # raw body lines
    footnotes: dict[int, str] = field(default_factory=dict)  # number -> text
    mode: str = "main"                    # frontmatter | toc | main | entries-* | raw
    label: str | None = None              # printed label, verbatim ("xiv", "312")
    index: int = -1                       # physical page, 1-based file ordinal
    label_top: str | None = None          # label candidate at top of the page
    label_bottom: str | None = None       # label candidate at bottom of the page
    # The label the document's own catalogue states (PDF PageLabels), measured
    # by the backend. reconcile_page_numbers believes it only where it agrees
    # with the labels actually detected on the printed pages.
    backend_label: str | None = None
    # A chapter title the outline states for this page and the page confirmed
    # (reflow/outline.py). Rendered as a heading before the page's text.
    heading: str | None = None
    # Small-type lines above the first definition of this page's footnote
    # block: the tail of a note that began on the previous page. Consumed by
    # attach_continuations, None afterwards.
    fn_continuation: str | None = None

    def __post_init__(self) -> None:
        # ``num`` is the ordinal, ``label`` the identity. For an arabic page the
        # two coincide, so callers that only know a number (tests, older code)
        # still get a usable label. reconcile_page_numbers sets both explicitly.
        if self.label is None and self.num >= 0:
            self.label = str(self.num)


# ----------------------------------------------------------------------
# 1) Parse page: split body / footnotes / page number
# ----------------------------------------------------------------------

def parse_page(
    text: str,
    fn_block: list[str] | None = None,
    *,
    geometry_verified: bool = False,
) -> Page | None:
    """Parse a single page file. Returns None if empty.

    ``fn_block`` carries the page's footnote block where the geometry already
    verified it (small type at the bottom, see ``split_small_type_block``).
    Inside such a block the ``NN.`` convention is trusted alongside ``NN)``;
    on bare text it never is.

    ``geometry_verified`` says the page was reassembled from measured lines.
    Then ``split_small_type_block`` has already looked for a footnote block and
    an empty ``fn_block`` is an answer, not a gap: the page carries no small
    type, so there is no block, and the bare ``NN)`` convention must not
    overrule that — a numbered list ("1) …") would otherwise swallow the page
    from its first item on. Without geometry (the TXT path) the convention is
    all we have and is trusted as before.
    """
    text = text.translate(SUPERSCRIPT_DIGITS)
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines and not fn_block:
        return None

    # Collect page-label candidates at the first AND last non-empty line.
    # The choice (top vs. bottom) is made globally by reconcile_page_numbers.
    label_top = None
    label_bottom = None
    if lines:
        lb = detect_page_label(lines[-1])
        if lb is not None:
            label_bottom = lb
            lines.pop()
    if lines:
        lt = detect_page_label(lines[0])
        if lt is not None:
            label_top = lt
            lines.pop(0)
    page_num = -1  # provisional; reconcile_page_numbers sets num and label

    # Footnote block: starting at the first line that begins with "NN)".
    # Only consulted where the geometry could not answer the question itself —
    # and a cut block answers it just as much as an empty one does. Running the
    # convention over a body the geometry already separated would let a
    # numbered list ("1) …") swallow the page from its first item on, which is
    # exactly the defect the empty case was fixed for.
    fn_start = None
    if not geometry_verified:
        for i, ln in enumerate(lines):
            if FOOTNOTE_RE.match(ln):
                fn_start = i
                break

    body_lines: list[str] = []
    fn_lines: list[str] = []
    if fn_start is None:
        body_lines = lines
    else:
        body_lines = lines[:fn_start]
        fn_lines = lines[fn_start:]

    # Assemble footnotes (join multi-line notes, dehyphenate)
    footnotes, _ = _assemble_footnotes(fn_lines, FOOTNOTE_RE.match)

    # The size-verified block from the page geometry. Lines above its first
    # definition are the tail of a note that began on the previous page.
    fn_continuation: str | None = None
    if fn_block:
        block = [ln.translate(SUPERSCRIPT_DIGITS).rstrip() for ln in fn_block]
        block_notes, leading = _assemble_footnotes(block, match_definition)
        footnotes.update(block_notes)
        if leading:
            fn_continuation = dehyphenate_join(leading).strip() or None

    # Replace footnote markers in the body with [NN] (in-place on body_lines)
    body_lines = substitute_markers(body_lines, footnotes)

    return Page(
        num=page_num,
        body_lines=body_lines,
        footnotes=footnotes,
        label_top=label_top,
        label_bottom=label_bottom,
        fn_continuation=fn_continuation,
    )


def _assemble_footnotes(
    fn_lines: list[str], matcher
) -> tuple[dict[int, str], list[str]]:
    """Join multi-line definitions, dehyphenated. Returns (notes, leading) —
    ``leading`` being the lines before the first definition start."""
    footnotes: dict[int, str] = {}
    leading: list[str] = []
    cur_num: int | None = None
    cur_buf: list[str] = []

    def flush():
        if cur_num is None:
            return
        footnotes[cur_num] = dehyphenate_join(cur_buf).strip()

    for ln in fn_lines:
        m = matcher(ln)
        if m:
            flush()
            cur_num = int(m.group(1))
            cur_buf = [m.group(2)]
        elif cur_num is None:
            leading.append(ln)
        else:
            cur_buf.append(ln)
    flush()
    return footnotes, leading


def attach_continuations(pages: list[Page]) -> int:
    """Reattach a definition that ran over the page break to its note.

    The continuation extends the highest-numbered note of the nearest earlier
    page that has any — footnotes print in reading order, so the note broken
    by the page edge is the last one begun. Returns how many were reattached;
    an unattachable continuation stays on its page for the audit to see.
    """
    attached = 0
    for i, page in enumerate(pages):
        if not page.fn_continuation:
            continue
        for prev in reversed(pages[:i]):
            if prev.footnotes:
                num = max(prev.footnotes)
                prev.footnotes[num] = dehyphenate_join(
                    [prev.footnotes[num], page.fn_continuation]
                )
                page.fn_continuation = None
                attached += 1
                break
    return attached


def _sequence_score(nums: list[int]) -> int:
    """Count adjacent +1 steps among the non-missing entries (in order).
    A higher score means the column forms a more consistent running pagination."""
    score = 0
    prev = None
    for n in nums:
        if n < 0:
            prev = None
            continue
        if prev is not None and n == prev + 1:
            score += 1
        prev = n
    return score


def _ordinal(label: str | None) -> int:
    """Sortable value of a label candidate; -1 when there is none."""
    if label is None:
        return -1
    n = decode_label(label)
    return -1 if n is None else n


# A catalogue column needs this many pages where both it and a printed label
# exist, agreeing at this rate, before it is believed. Below that, the printed
# pages stand: scan tooling generates catalogues mechanically (physical =
# printed), and believing one shifts every citation in the book.
MIN_BACKEND_OVERLAP = 3
BACKEND_AGREEMENT = 0.8


def reconcile_page_numbers(pages: list[Page]) -> str:
    """Choose, globally, whether the book paginates at the top or the bottom,
    and set each page's ``label`` and ``num`` from the winning column.

    The winner is the column whose candidates form the longer consistent
    ascending run (sequence variant). Safe fallback: on a tie or no signal,
    prefer the bottom column (the historical behaviour), else leave the page
    unlabelled — never invent a number.

    Scoring runs on the decoded ordinals, so a roman frontmatter run (i, ii, …)
    scores like an arabic one. The label itself stays verbatim: it is what makes
    the page citable, and roman ``xiv`` must not become arabic ``14``.
    """
    top_labels = [p.label_top for p in pages]
    bottom_labels = [p.label_bottom for p in pages]
    top = [_ordinal(lbl) for lbl in top_labels]
    bottom = [_ordinal(lbl) for lbl in bottom_labels]
    top_score = _sequence_score(top)
    bottom_score = _sequence_score(bottom)
    has_top = any(n >= 0 for n in top)
    has_bottom = any(n >= 0 for n in bottom)

    if not has_top and not has_bottom:
        # Without printed labels there is nothing to verify a catalogue column
        # against — and an unverified catalogue is exactly the thing scan
        # tooling generates mechanically. Stay unlabelled rather than guess.
        return "none"
    if top_score > bottom_score:
        chosen_labels, chosen_nums, col = top_labels, top, "top"
    elif bottom_score > top_score:
        chosen_labels, chosen_nums, col = bottom_labels, bottom, "bottom"
    else:  # tie — prefer whichever column actually has labels, bottom first
        if has_bottom:
            chosen_labels, chosen_nums, col = bottom_labels, bottom, "bottom"
        else:
            chosen_labels, chosen_nums, col = top_labels, top, "top"

    # The catalogue column (PDF PageLabels) wins where it demonstrably agrees
    # with the printed pages: it knows the pages the detector must guess — a
    # chapter opening shows no running head, only the big chapter number.
    backend_labels = [p.backend_label for p in pages]
    both = [
        (b, c)
        for b, c in zip(backend_labels, chosen_labels)
        if b is not None and c is not None
    ]
    agree = sum(1 for b, c in both if b.strip().lower() == c.strip().lower())
    if len(both) >= MIN_BACKEND_OVERLAP and agree >= BACKEND_AGREEMENT * len(both):
        for p, backend, lbl, n in zip(pages, backend_labels, chosen_labels, chosen_nums):
            ordinal = _ordinal(backend) if backend is not None else -1
            if ordinal >= 0:
                p.num, p.label = ordinal, backend
            else:
                p.num, p.label = n, (lbl if n >= 0 else None)
        return f"backend catalogue (agrees with {col} on {agree}/{len(both)} pages)"

    for p, lbl, n in zip(pages, chosen_labels, chosen_nums):
        p.num = n
        p.label = lbl if n >= 0 else None
    return col


# ----------------------------------------------------------------------
# 2) Helper functions: de-hyphenation
# ----------------------------------------------------------------------

# Short German connecting words before which a hyphen is kept (a compound
# with an elided base word, e.g. 'Einzel- und Gesamt…').
KEEP_HYPHEN_BEFORE = re.compile(
    r"^(und|oder|bis|sowie|wie|als|zur?|zum?|noch|aber)\b", re.IGNORECASE
)


def is_hard_hyphen(prev: str, next_line: str) -> bool:
    """True if the '-' at the end of prev is a genuine compound hyphen (should
    be kept), False for a line-break hyphen (should disappear)."""
    return bool(KEEP_HYPHEN_BEFORE.match(next_line.lstrip()))


def dehyphenate_join(lines: list[str]) -> str:
    """Join lines; resolves 'word-\\n' into 'word'."""
    out = []
    for i, ln in enumerate(lines):
        if i == 0:
            out.append(ln)
            continue
        prev = out[-1]
        if (
            prev.endswith("-")
            and len(prev) >= 2
            and prev[-2].isalpha()
            and ln[:1].isalpha()
            and not is_hard_hyphen(prev, ln)
        ):
            out[-1] = prev[:-1] + ln.lstrip()
        else:
            out[-1] = prev + " " + ln.lstrip()
    return out[0] if out else ""


# ----------------------------------------------------------------------
# 3) Calibration: determine the line-length threshold for paragraph ends
# ----------------------------------------------------------------------

# Sane fallback threshold when the main-page histogram is empty/degenerate —
# better to under-break paragraphs than to return 0 (which breaks at every line).
CALIB_FALLBACK_MIN = 40

# ----------------------------------------------------------------------
# Region/mode detection
# ----------------------------------------------------------------------

# Heading patterns that trigger a mode change.
# The first 10 non-empty body lines of a page are checked.
HEADING_TRIGGERS = [
    (re.compile(
        r"^(INHALTSVERZEICHNIS|INHALT|CONTENTS|TABLE OF CONTENTS|"
        r"TABLE DES MATIÈRES|SOMMAIRE|INDICE|SOMMARIO|ÍNDICE)\s*$",
        re.IGNORECASE,
    ), "toc"),
    # Bibliography: capitalized surnames at the start of a line are clear markers
    (re.compile(r"^\d+\.\s+Literatur\s*$"), "entries-versal"),
    # Abbreviations / sources / indexes: OCR column scan often broken -> leave as raw
    (re.compile(
        r"^\d+\.\s+(Abkürzungsverzeichnis|Quellen|Personenregister|Sachregister|Ortsregister)\s*$"
    ), "raw"),
]


# Prose classifier: a page counts as running text if at least PROSE_MIN_LINES
# non-empty body lines exist and a sufficient fraction of them lies near the
# dominant body width (± PROSE_BAND).
PROSE_MIN_LINES = 5
PROSE_BAND = 0.30          # ±30% of the dominant width counts as a "full line"
PROSE_FRACTION = 0.5       # this fraction of full lines makes a page prose


def estimate_body_width(pages: list[Page]) -> int:
    """Dominant body line width across all pages (most common length)."""
    lengths: Counter[int] = Counter()
    for p in pages:
        for ln in p.body_lines:
            if ln.strip():
                lengths[len(ln.rstrip())] += 1
    if not lengths:
        return 0
    return lengths.most_common(1)[0][0]


def is_prose_page(
    page: Page,
    width: int,
    *,
    min_lines: int = PROSE_MIN_LINES,
    band: float = PROSE_BAND,
) -> bool:
    """True if the page consists mostly of lines near ``width``."""
    if width <= 0:
        return False
    body = [len(ln.rstrip()) for ln in page.body_lines if ln.strip()]
    if len(body) < min_lines:
        return False
    lo = width * (1 - band)
    full = sum(1 for n in body if n >= lo)
    return full / len(body) >= PROSE_FRACTION


def assign_modes(pages: list[Page]) -> None:
    """Sets p.mode for every page based on detected region transitions.

    Starting mode is 'frontmatter'. Heading triggers switch to toc/entries/raw.
    The frontmatter->main transition is hybrid: it fires on the first page
    that either looks like running text (is_prose_page) OR carries book page 1
    — this correctly detects volumes without an arabic-1 trigger (Snell),
    without losing the previous behaviour (safe fallback).
    """
    from scriptor.reflow.toc import is_toc_page
    width = estimate_body_width(pages)
    mode = "frontmatter"
    for p in pages:
        # A confirmed outline heading was cut off the page's body — the mode
        # triggers must still see it ("Contents" cut away would let the
        # contents page reflow as prose).
        candidates = ([p.heading.strip()] if p.heading else []) + [
            ln.strip() for ln in p.body_lines if ln.strip()
        ][:10]
        triggered = False
        for line in candidates:
            for pat, new_mode in HEADING_TRIGGERS:
                if pat.match(line):
                    mode = new_mode
                    triggered = True
                    break
            if triggered:
                break
        if not triggered:
            if mode == "frontmatter" and is_toc_page(p):
                mode = "toc"
            elif mode in ("frontmatter", "toc") and (is_prose_page(p, width) or p.label == "1"):
                mode = "main"
        p.mode = mode


def calibrate_threshold(pages: list[Page], peak_fraction: float = 0.25) -> tuple[int, Counter[int]]:
    """
    Collects the lengths of all body lines, determines the left edge of the
    main peak ('full running-text lines'), and derives from it the maximum
    value at which a line still counts as 'suspiciously short'.

    Procedure:
      1. Find the mode of line lengths (= most common length, typical full width)
      2. Walk left from the mode until count < peak_fraction × peak_count
      3. That position is the left edge; threshold = position − 1.

    Long tails (indexes, headings) and a possible second peak in the
    footnotes do not affect the result.
    """
    lengths: Counter[int] = Counter()
    for p in pages:
        if not p.body_lines or p.mode != "main":
            continue
        # Exclude the last line of each page — almost always short due to layout
        for ln in p.body_lines[:-1]:
            if ln.strip():
                lengths[len(ln)] += 1

    if not lengths:
        return CALIB_FALLBACK_MIN, lengths

    mode_len, mode_count = lengths.most_common(1)[0]
    cutoff = mode_count * peak_fraction
    left_edge = mode_len
    for ln_len in range(mode_len, 0, -1):
        if lengths.get(ln_len, 0) < cutoff:
            left_edge = ln_len + 1
            break
    threshold = left_edge - 1
    return threshold, lengths


# ----------------------------------------------------------------------
# 4) Process body: paragraph reconstruction + insert page markers
# ----------------------------------------------------------------------

# Simple sentence-end detection. Both curly double quotes close sentences:
# German quotations end on “ („…“), English ones on ” (“…”) — Zuckerman.
SENT_END = re.compile(r"[.!?»“”\"’']$")

# Placed footnote markers at the end of a line ("… Occident.” [1]" or even
# "… country. [4] [5]"). They stand *after* the full stop and would hide it
# from SENT_END — the paragraph-end check looks at the line without them.
_TRAILING_MARKERS = re.compile(r"(\s*\[\d{1,3}\])+$")


# Numbered heading at the start of a paragraph: "3.4. Probleme um Welf VI." and,
# as scholarly articles number them, "2.1 Retrieval Strategies" without the
# period. Heading level = number of periods in the numbering + 1.
#
# Each group is at most two digits, which keeps a year out: a bibliography entry
# continues "… and Stéphane Clinchant. 2021. SPLADE v2: Sparse Lexical …", and a
# document with 2021 sections does not exist. Dropping the period costs the
# single-number case: "44 The Surrender of Narbonne" is Zuckerman's folio and its
# running head, not chapter 44, so a number without a period needs a subsection
# to prove it is one.
HEADING_RE = re.compile(
    r"^(?:(\d{1,2}(?:\.\d{1,2}){0,3})\.|(\d{1,2}(?:\.\d{1,2}){1,3}))\s+[A-ZÄÖÜ]"
)
HEADING_MAX_LEN = 80


# What emphasis alone is allowed to turn into a heading: a subsection ("4.1 …",
# with or without a period) or a single number *without* one ("3 Methodology", the
# way articles set them). A single number with a period stays out — "16. Jahrhundert"
# is an ordinal, and a scan whose italics are unreliable prints plenty of those.
MARKED_HEADING_RE = re.compile(
    r"^(?:(\d{1,2}(?:\.\d{1,2}){1,3})\.?|(\d{1,2}))\s+[^\W\d_]"
)

# The list bullets this corpus prints, at the head of a line. Dashes are left
# out: a line opening with one is far more often a dialogue or a dash than an
# item, and breaking there would cut prose apart.
BULLET_RE = re.compile(r"^[•▪◦‣]\s*\S")

# Imported by value so the hot line loop does not import per line.
from scriptor.reflow.headings import MARK as HEADING_MARK  # noqa: E402
from scriptor.reflow.tables import BREAK as TABLE_BREAK  # noqa: E402


def heading_level(line: str, *, marked: bool = False) -> int:
    """0 if not a heading, otherwise level 1-4.

    ``marked`` says the typesetter set this whole line apart (``reflow/headings``).
    That is what a single number without a period needs: by text alone it cannot
    be told from a folio in front of a running head.
    """
    if len(line) > HEADING_MAX_LEN:
        return 0
    if marked:
        m = MARKED_HEADING_RE.match(line)
        if m:
            return (m.group(1) or m.group(2)).count(".") + 1
        # Marked and unnumbered: "Abstract", "References", "A Per-Category
        # Accuracy" — the top level of their document. A line opening with a digit
        # is not one of them: "16. Jahrhundert" is an ordinal in a work title.
        return 0 if line[:1].isdigit() else 1
    m = HEADING_RE.match(line)
    if not m:
        return 0
    return (m.group(1) or m.group(2)).count(".") + 1


def reconstruct_body(
    pages: list[Page],
    threshold: int,
    audit: dict[str, list[int]] | None = None,
) -> tuple[list[str], list[dict[FnKey, str]], list[dict[int, FnKey]], list[int]]:
    """
    Returns a list of paragraph strings (body, with [p.NN] markers and
    [NN] footnote markers), and in parallel, per paragraph, a dict with the
    associated footnote texts and a heading level (0 = normal paragraph).

    Footnotes whose marker was not found on the page (OCR error at the
    marker, not at the definition) are appended to the relevant paragraph
    at the end of the page, so they are not lost. The affected pages are
    additionally recorded in `audit[page_num] = [nums…]`.
    """
    if audit is None:
        audit = {}
    paragraphs: list[str] = []
    para_footnotes: list[dict[FnKey, str]] = []
    # Per paragraph: which [N] occurrence (counted left to right, 0-based) belongs
    # to which footnote. The occurrence index is what disambiguates two notes that
    # print the same number on different pages; the number in the text cannot.
    para_occurrences: list[dict[int, FnKey]] = []
    para_levels: list[int] = []

    cur_chunks: list[str] = []                 # word blocks of the current paragraph
    cur_fn: dict[FnKey, str] = {}              # footnotes of this paragraph
    cur_occ: dict[int, FnKey] = {}             # marker occurrence -> footnote
    occ_index = 0                              # [N] occurrences seen in this paragraph
    pending_hyphen = False                     # previous chunk ends on a line-break hyphen
    pending_page_marker: str | None = None     # [p. NN] not yet inserted

    def end_paragraph(level: int = 0):
        nonlocal cur_chunks, cur_fn, cur_occ, occ_index, pending_hyphen
        text = "".join(cur_chunks).strip()
        text = re.sub(r"[ \t]+", " ", text)
        if text:
            paragraphs.append(text)
            para_footnotes.append(cur_fn)
            para_occurrences.append(cur_occ)
            para_levels.append(level)
        cur_chunks = []
        cur_fn = {}
        cur_occ = {}
        occ_index = 0
        pending_hyphen = False
        # Do NOT reset pending_page_marker: a page marker not yet placed (e.g.
        # because the first body line after the removed running head is empty)
        # must be kept until the first word. It is consumed exclusively by
        # flush_page_marker, or reset (overwritten) at the start of each page.

    def flush_page_marker():
        nonlocal pending_page_marker
        if pending_page_marker is None:
            return
        if cur_chunks:
            cur_chunks.append(" ")
        cur_chunks.append(pending_page_marker)
        pending_page_marker = None

    def append_word_segment(seg: str):
        """Append with correct handling of a line-break hyphen and any
        pending page marker."""
        nonlocal pending_hyphen
        if not seg:
            return
        if pending_hyphen:
            cur_chunks.append(seg)            # no space, completes the word
            pending_hyphen = False
            flush_page_marker()               # insert the marker only after the word
        else:
            flush_page_marker()
            if cur_chunks:
                cur_chunks.append(" ")
            cur_chunks.append(seg)

    # The page position within this reconstruction, not Page.index: the key only
    # has to separate two pages of this run, and depending on a field some callers
    # never populate would let the collision back in unnoticed.
    for page_pos, p in enumerate(pages):
        if not p.body_lines or p.mode != "main":
            continue

        # Note the page marker; insert it after any word left open
        if p.label is not None:
            pending_page_marker = f"[p. {p.label}]"

        # A confirmed chapter start: close whatever paragraph is running and
        # set the title as its own heading block. The page marker is not
        # pulled into the heading — it stays noted for the following text.
        if p.heading:
            end_paragraph()
            saved_marker = pending_page_marker
            pending_page_marker = None
            cur_chunks.append(p.heading)
            end_paragraph(level=1)
            pending_page_marker = saved_marker

        seen_this_page: set[int] = set()
        paragraphs_before_page = len(paragraphs)

        n = len(p.body_lines)
        for i, ln in enumerate(p.body_lines):
            stripped = ln.rstrip()
            # The typographic mark travels with the line and never into the text.
            marked = stripped.startswith(HEADING_MARK)
            stripped = stripped.lstrip(HEADING_MARK)
            if not stripped.strip():
                # Empty line in the middle of the body -> end of paragraph
                end_paragraph()
                continue

            # A line the typesetter set apart continues nothing: it closes the
            # paragraph still running. Columns end mid-sentence often enough that
            # requiring an empty paragraph would swallow half the headings.
            if marked and not pending_hyphen and cur_chunks:
                if heading_level(stripped, marked=True) > 0:
                    saved_marker = pending_page_marker
                    pending_page_marker = None
                    end_paragraph()
                    pending_page_marker = saved_marker

            # A bullet opens an item, and an item is a paragraph. Without this the
            # first item of a list runs on from the sentence that introduces it —
            # the bullet shares its printed line with its own text, so no line
            # break marks the boundary the way it does for every item after it.
            if BULLET_RE.match(stripped) and cur_chunks and not pending_hyphen:
                saved_marker = pending_page_marker
                pending_page_marker = None
                end_paragraph()
                pending_page_marker = saved_marker

            # Numbered heading at the start of a paragraph (only if no word is
            # still open and no paragraph is running) -> its own block.
            # A pending page marker is NOT pulled into the heading, but stays
            # noted for the following paragraph.
            if not cur_chunks and not pending_hyphen:
                lvl = heading_level(stripped, marked=marked)
                if lvl > 0:
                    saved_marker = pending_page_marker
                    pending_page_marker = None
                    cur_chunks.append(stripped)
                    end_paragraph(level=lvl)
                    pending_page_marker = saved_marker
                    continue

            # Line-break hyphen at the end? (only if the next line does NOT
            # start with 'und/oder/...' — otherwise it's a compound hyphen)
            ends_hyphen = (
                len(stripped) >= 2 and stripped.endswith("-")
                and stripped[-2].isalpha()
            )
            if ends_hyphen and i + 1 < n:
                if is_hard_hyphen(stripped, p.body_lines[i + 1]):
                    ends_hyphen = False
            content = stripped[:-1] if ends_hyphen else stripped

            # Register already-placed [NN] markers so they migrate to the end of
            # the paragraph. Every occurrence is counted, whether or not this page
            # defines that number, so the index stays aligned with the [N] matches
            # the renderer will walk over the finished paragraph text.
            for m in PLACED_MARKER_RE.finditer(content):
                num = int(m.group(1))
                if num in p.footnotes:
                    key = (page_pos, num)
                    cur_fn[key] = p.footnotes[num]
                    cur_occ[occ_index] = key
                    seen_this_page.add(num)
                occ_index += 1

            append_word_segment(content)

            if ends_hyphen:
                pending_hyphen = True
            else:
                pending_hyphen = False
                # Paragraph-end heuristic: short line + sentence-end punctuation.
                # Even the last line of a page may end a paragraph — if it really
                # was a paragraph, this ends it here; if not, the next paragraph
                # simply continues on the following page (in practice this
                # happens less often than genuine paragraph ends at the page foot).
                # Markers sit after the closing punctuation; strip them for the
                # check, but keep their length out of the width measure too —
                # "[N]" is not printed on the page.
                bare = _TRAILING_MARKERS.sub("", stripped)
                if len(bare) <= threshold and SENT_END.search(bare):
                    end_paragraph()

        # End of page: rescue this page's unanchored footnotes.
        # They land in the last-touched paragraph (open, or last closed
        # during this page). The renderer appends them as a hanging
        # reference — so they are not lost.
        unclaimed = sorted(set(p.footnotes) - seen_this_page)
        if unclaimed and p.label is not None:
            audit[p.label] = unclaimed
            if cur_chunks:
                target = cur_fn
            elif len(paragraphs) > paragraphs_before_page:
                target = para_footnotes[-1]
            else:
                # Page contains only footnote definitions without its own body
                # (or the body only continues an already-closed paragraph
                # from the previous page) — attach to the next paragraph.
                target = cur_fn
            for num in unclaimed:
                target[(page_pos, num)] = p.footnotes[num]

    end_paragraph()
    return paragraphs, para_footnotes, para_occurrences, para_levels


def _local_view(fns: dict[FnKey, str]) -> dict[int, str]:
    """The printed footnote numbers of a paragraph, as the confidence layer sees
    them. Where a paragraph spans a page break and both pages print the same
    number, the entries merge; the texts stay distinct in ``fns``."""
    return {num: text for (_pg, num), text in fns.items()}


def document_evidence(pages: list[Page], threshold: int, profile=None):
    """Count, over the whole document, which glyph stands for which digit.

    Reconstructs a second time on purpose: the statistics must span every main
    paragraph, not only the group being rendered, and they must be a pure function
    of the source pages. Same pages, same evidence, same output, same decision file.

    ``profile`` adds pseudo-observations from volumes a human already corrected —
    an explicit input, so the run stays reproducible. See ``reflow/profile.py``.
    """
    from scriptor.reflow.confidence import collect_evidence

    paras, fns, _occs, _levels = reconstruct_body(pages, threshold)
    pseudo = profile.pseudo_counts() if profile else None
    return collect_evidence(paras, [_local_view(f) for f in fns], pseudo=pseudo)


def apply_decisions(
    paragraphs: list[str],
    para_footnotes: list[dict[FnKey, str]],
    para_occurrences: list[dict[int, FnKey]],
    decisions,
    evidence=None,
) -> tuple[list[str], list[dict[int, FnKey]]]:
    """Place a real marker wherever the human accepted a candidate glyph.

    The glyph is what OCR made of the superscript digit, so it is *replaced* by
    the marker rather than kept beside it. Inserting a marker shifts the [N]
    occurrences after it, so ``para_occurrences`` is rebuilt from the offsets —
    getting this wrong would reassign footnotes to the wrong pages, which is the
    very failure ``FnKey`` exists to prevent.

    ``evidence`` must be the same one the decision file was written from, or
    "cand 1" would name a different glyph than the one the human chose.

    A decision that no longer matches a candidate is reported, never guessed.
    """
    from scriptor.reflow.confidence import analyse_paragraph

    new_paragraphs = list(paragraphs)
    new_occurrences = list(para_occurrences)

    for i, (para, fns, occs) in enumerate(zip(paragraphs, para_footnotes, para_occurrences)):
        local = _local_view(fns)
        claimed = set(occs.values())
        replacements: list[tuple[tuple[int, int], int, FnKey]] = []

        for a in analyse_paragraph(para, local, evidence=evidence):
            ref = (a.page, a.fn_num)
            index = decisions.accepted.get(ref)
            if index is None:
                continue
            if not a.candidates or not 1 <= index <= len(a.candidates):
                decisions.unmatched.append(ref)
                continue
            # Which footnote of ``fns`` is this? The one with that printed number
            # that no marker has claimed yet. Two unclaimed notes with the same
            # number in one paragraph cannot be told apart — report, do not pick.
            keys = [k for k in fns if k[1] == a.fn_num and k not in claimed]
            if len(keys) != 1:
                decisions.unmatched.append(ref)
                continue
            replacements.append((a.candidates[index - 1].span, a.fn_num, keys[0]))
            decisions.applied.append(ref)

        if not replacements:
            continue

        # Existing markers keep their key; accepted candidates add one. Ordering
        # by offset reproduces the order the renderer will walk the new text in.
        existing = [
            (m.start(), occs.get(pos))
            for pos, m in enumerate(PLACED_MARKER_RE.finditer(para))
        ]
        added = [(span[0], key) for span, _num, key in replacements]
        ordered = sorted(existing + added, key=lambda t: t[0])
        new_occurrences[i] = {
            pos: key for pos, (_off, key) in enumerate(ordered) if key is not None
        }

        text = para
        for (start, end), num, _key in sorted(replacements, key=lambda r: r[0][0], reverse=True):
            text = text[:start] + f"[{num}]" + text[end:]
        new_paragraphs[i] = text

    return new_paragraphs, new_occurrences


# ----------------------------------------------------------------------
# 5) Region-specific renderers
# ----------------------------------------------------------------------

VERSAL_RE = re.compile(r"^[A-ZÄÖÜ]{2,}")
CAP_RE = re.compile(r"^[A-ZÄÖÜ][a-zäöü]")


def format_paragraph_txt(para: str, fns: dict[FnKey, str], level: int) -> str:
    """TXT mode: paragraph + footnotes indented at the end of the paragraph.

    Ordered by page, then by the number printed on that page; the number shown is
    the printed one, so it can be checked against the scan.
    """
    out = [para]
    for (_page, num) in sorted(fns):
        out.append(f"{INDENT}[{num}] {fns[(_page, num)]}")
    return "\n".join(out)


# Literal * and _ in the source text (FineReader renders the ʿayn of Arabic
# transliterations as an asterisk: "*Abbasid") would pair up into Markdown
# emphasis — the characters vanish from the reading view and the text between
# them turns italic. Escaped, they stay visible verbatim. Our own constructs
# ([^N], [p. …], leading #) never contain these characters.
_MD_LITERALS = re.compile(r"[*_]")


def escape_md(text: str) -> str:
    return _MD_LITERALS.sub(lambda m: "\\" + m.group(0), text)


# One pass over synthetic-anchor sentinels and placed [N] markers together, so
# global numbers are assigned in final reading order and the definitions stay
# in anchor order. Group 1 is the sentinel index, group 2 the printed number.
_COMBINED_MARKER_RE = re.compile("\x00(\\d+)\x00|" + PLACED_MARKER_RE.pattern)


def format_paragraph_md(
    para: str,
    fns: dict[FnKey, str],
    occurrences: dict[int, FnKey],
    level: int,
    state: dict,
    page_order: dict[str, int] | None = None,
) -> str:
    """
    MD mode: [N] markers in the paragraph text become [^G] Pandoc markers with
    global numbering (because Markdown footnote IDs must be unique across the
    whole document — Hechberger's per-chapter reset would otherwise break this).
    The defs are collected in state["defs"] and emitted at the end of the
    document. Headings (level > 0) get a leading #.

    Each [N] is resolved by its *position*, not by the number it shows: within one
    paragraph the same number can belong to two different footnotes, one per page.
    ``occurrences`` maps the position to the footnote; positions it does not cover
    are markers this page never defined, and they are left untouched.

    Footnotes whose marker was not found in the text get a synthetic anchor at
    the upper bound of the interval in which the lost marker can lie
    (PREPARED_FORMAT_SPEC §4.3): before the next placed marker of the same
    page where one follows, otherwise before the first marker of a following
    page (``page_order``: printed label -> page position, same positions as
    the FnKey page component), otherwise at the end of the paragraph. Several
    anchors sharing a bound stand there in ascending printed-number order.
    """
    para = escape_md(para)

    placed_keys = set(occurrences.values())
    hanging = [k for k in sorted(fns) if k not in placed_keys]
    sentinel_keys: list[FnKey] = []
    if hanging:
        marker_starts = [m.start() for m in PLACED_MARKER_RE.finditer(para)]
        page_marks = list(PAGE_MARKER_RE.finditer(para))
        bounds: list[tuple[int, int, FnKey]] = []
        for key in hanging:
            pg, num = key
            offset = len(para)
            same_page = [
                marker_starts[i]
                for i, k in occurrences.items()
                if k[0] == pg and k[1] > num and i < len(marker_starts)
            ]
            if same_page:
                offset = min(same_page)
            else:
                for m in page_marks:
                    later = (page_order or {}).get(m.group(1))
                    if later is not None and later > pg:
                        offset = m.start()
                        break
            bounds.append((offset, num, key))
        ordered = sorted(bounds)
        sentinel_keys = [key for _off, _num, key in ordered]
        for i in range(len(ordered) - 1, -1, -1):
            offset = ordered[i][0]
            para = para[:offset] + f" \x00{i}\x00" + para[offset:]

    num_map: dict[FnKey, int] = {}
    seen = 0

    def assign(key: FnKey) -> int:
        if key not in num_map:
            state["counter"] += 1
            num_map[key] = state["counter"]
            state["defs"].append(f"[^{state['counter']}]: {escape_md(fns[key])}")
        return num_map[key]

    def repl(m: re.Match) -> str:
        nonlocal seen
        if m.group(1) is not None:
            return f"[^{assign(sentinel_keys[int(m.group(1))])}]"
        position = seen
        seen += 1
        key = occurrences.get(position)
        if key is None:
            return m.group(0)
        return f"[^{assign(key)}]"

    new_para = _COMBINED_MARKER_RE.sub(repl, para)
    # The sentinel carries a leading space; collapse the doubling where the
    # insertion point already had one, and trim the end-of-paragraph case.
    new_para = re.sub(r" {2,}", " ", new_para).rstrip()

    if level > 0:
        return ("#" * min(level, 6)) + " " + new_para
    return new_para


def render_main(
    pages: list[Page],
    threshold: int,
    fmt: str,
    state: dict,
    audit: dict[str, list[int]],
    annotator=None,
    decisions=None,
    evidence=None,
) -> list[str]:
    paras, fns, occs, levels = reconstruct_body(pages, threshold, audit)
    if decisions:
        # Before the annotator: a footnote whose marker has just been placed is no
        # longer uncertain, so it must not be flagged again.
        paras, occs = apply_decisions(paras, fns, occs, decisions, evidence)
    if annotator is not None:
        # The confidence layer reasons about the numbers printed on the page, so
        # it gets the printed-number view. Where a paragraph spans a page break and
        # both pages print the same number, the views merge — the layer then simply
        # sees the number as present and does not flag it. Under-flagging, not
        # corruption: the texts themselves stay distinct in ``fns``.
        paras = [
            annotator.annotate(p, _local_view(f), evidence) for p, f in zip(paras, fns)
        ]
    if fmt == "md":
        # Printed label -> page position, aligned with the FnKey page component
        # (reconstruct_body enumerates this same list). First occurrence wins.
        page_order: dict[str, int] = {}
        for i, p in enumerate(pages):
            if p.label is not None:
                page_order.setdefault(p.label, i)
        return [
            format_paragraph_md(p, f, o, lvl, state, page_order)
            for p, f, o, lvl in zip(paras, fns, occs, levels)
        ]
    return [
        format_paragraph_txt(p, f, lvl) for p, f, lvl in zip(paras, fns, levels)
    ]


def render_frontmatter(pages: list[Page]) -> list[str]:
    """Front matter: original lines preserved, one block per page."""
    blocks: list[str] = []
    for p in pages:
        if not p.body_lines:
            continue
        marker = f"[p. {p.label}]\n" if p.label is not None else ""
        blocks.append(marker + "\n".join(p.body_lines).rstrip())
    return blocks


def render_entries(pages: list[Page], start_re: re.Pattern[str]) -> list[str]:
    """
    List-like region (bibliography, index, abbreviations).
    An entry = a contiguous block starting with start_re;
    following lines are appended dehyphenated.
    """
    entries: list[str] = []
    cur: list[str] = []
    pending_hyphen = False
    pending_page: str | None = None

    def flush():
        nonlocal cur, pending_hyphen
        if cur:
            entries.append("".join(cur).rstrip())
        cur = []
        pending_hyphen = False

    def append_seg(seg: str):
        nonlocal pending_hyphen, pending_page
        if not seg:
            return
        if pending_hyphen:
            cur.append(seg)
            pending_hyphen = False
        else:
            if cur:
                cur.append(" ")
            cur.append(seg)
        if pending_page is not None:
            cur.append(" " + pending_page)
            pending_page = None

    for p in pages:
        if p.label is not None:
            pending_page = f"[p. {p.label}]"
        n = len(p.body_lines)
        for i, ln in enumerate(p.body_lines):
            stripped = ln.rstrip()
            if not stripped.strip():
                continue
            if start_re.match(stripped) and not pending_hyphen:
                flush()
            ends_hyphen = (
                len(stripped) >= 2 and stripped.endswith("-")
                and stripped[-2].isalpha()
            )
            if ends_hyphen and i + 1 < n:
                if is_hard_hyphen(stripped, p.body_lines[i + 1]):
                    ends_hyphen = False
            content = stripped[:-1] if ends_hyphen else stripped
            append_seg(content)
            pending_hyphen = ends_hyphen
    flush()
    return entries


def render_book(
    pages: list[Page],
    threshold: int,
    fmt: str = "txt",
    annotator=None,
    decisions=None,
    evidence=None,
) -> tuple[str, dict[str, list[int]]]:
    """Group pages by mode in source order and render each group accordingly.

    Returns the rendered document plus an audit dict of pages on which at
    least one footnote definition had no marker in the body.
    """
    from scriptor.reflow.toc import render_toc, inject_page_anchors

    if evidence is None:
        # Pass one over the whole document, so a glyph the book repeats is known
        # before the first paragraph is scored. Callers that render twice should
        # compute it once and pass it, or the two renders could rank candidates
        # differently.
        evidence = document_evidence(pages, threshold)

    out_blocks: list[str] = []
    state: dict = {"counter": 0, "defs": []}
    audit: dict[str, list[int]] = {}
    available_pages = {p.label for p in pages if p.label is not None}
    anchor_targets: set[str] = set()
    i = 0
    while i < len(pages):
        mode = pages[i].mode
        j = i
        while j < len(pages) and pages[j].mode == mode:
            j += 1
        group = pages[i:j]

        if mode == "main":
            out_blocks.extend(
                render_main(
                    group, threshold, fmt, state, audit, annotator, decisions, evidence
                )
            )
        elif mode in ("frontmatter", "raw"):
            out_blocks.extend(render_frontmatter(group))
        elif mode == "toc":
            tr = render_toc(group, available_pages)
            out_blocks.extend(tr.blocks)
            anchor_targets |= tr.anchor_targets
        elif mode == "entries-versal":
            out_blocks.extend(render_entries(group, VERSAL_RE))
        else:
            out_blocks.extend(render_frontmatter(group))

        i = j

    result = "\n\n".join(out_blocks).rstrip()
    if fmt == "md" and state["defs"]:
        result += "\n\n" + "\n\n".join(state["defs"])
    if fmt == "md" and anchor_targets:
        result = inject_page_anchors(result, anchor_targets)
    # Both internal marks are resolved here, where every render path meets. The
    # heading mark is dropped (reconstruct_body has read it off the line it
    # belongs to); a folded table's row breaks become the newlines they stand
    # for, and the table needs a blank line around it to be one in Markdown.
    result = result.replace(HEADING_MARK, "")
    if TABLE_BREAK in result:
        result = re.sub(
            rf"[ \t]*{TABLE_BREAK}[ \t]*", "\n", result
        )
    return result + "\n", audit


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main(
    src_dir: str,
    out_path: str,
    fmt: str | None = None,
    decisions_path: str | None = None,
    profile_path: str | None = None,
) -> None:
    from scriptor.reflow import decisions as decisions_mod
    from scriptor.reflow import profile as profile_mod

    decisions = (
        decisions_mod.load(decisions_path) if decisions_path else decisions_mod.Decisions()
    )
    ocr_profile = profile_mod.load(profile_path) if profile_path else None
    if ocr_profile:
        print(
            f"OCR profile: {profile_path} "
            f"({plural(len(ocr_profile.sources), 'source')}, "
            f"{plural(len(ocr_profile.digits()), 'digit')})",
            file=sys.stderr,
        )

    from scriptor.page import load_pages
    from scriptor.reflow.textlines import reconstruct

    src = Path(src_dir)
    source_pages = load_pages(src)
    print(f"Reading {plural(len(source_pages), 'page')} from {src}…", file=sys.stderr)

    if fmt is None:
        fmt = "md" if out_path.lower().endswith(".md") else "txt"
    print(f"Output format: {fmt}", file=sys.stderr)

    # Printed lines, where the backend measured them. A page whose lines carry no
    # baseline is passed through unchanged — that is the TXT path, and it is exactly
    # today's behaviour. Which of the two happened is reported, never assumed: a
    # line-length histogram built from fragments yields plausible, wrong paragraphs
    # and says nothing about it.
    # Two columns share one baseline grid, so the assembly above has to know about
    # the lane before it clusters, not after: joining across it interleaves the two
    # columns word for word. The lane is measured over the whole document, because
    # a single page's full-width table would hide it.
    from scriptor.reflow.columns import find_gutter

    gutter = find_gutter(source_pages)
    if gutter is not None:
        print(
            f"Two-column layout: gutter at {gutter.x0:.1f}–{gutter.x1:.1f}pt; "
            f"columns are read one after the other",
            file=sys.stderr,
        )
    reconstructions = [reconstruct(sp, gutter=gutter) for sp in source_pages]
    measured = sum(1 for r in reconstructions if r.measured)
    print(
        f"{measured} of {len(reconstructions)} pages reassembled from geometry",
        file=sys.stderr,
    )
    wide_gaps = sum(1 for r in reconstructions if r.wide_gap_lines)
    if wide_gaps:
        print(
            f"{wide_gaps} pages hold a line with a column-wide horizontal gap; "
            f"if this book is set in two columns, the reassembled lines are unreliable",
            file=sys.stderr,
        )
    # Cut the size-verified footnote block first, while lines and sizes are
    # still parallel — the running-element stripper below edits lines and
    # would silently desynchronise the two. The body size is calibrated over
    # the whole document: a note-heavy page's own dominant size would flip to
    # the footnote size and see nothing small.
    from scriptor.reflow.footnotes import dominant_size
    doc_body_size = dominant_size(
        [ln for r in reconstructions for ln in r.lines],
        [s for r in reconstructions for s in r.sizes],
    )
    if doc_body_size is not None:
        print(f"Dominant type size: {doc_body_size}pt", file=sys.stderr)
    splits = [
        split_small_type_block(r.lines, r.sizes, body_size=doc_body_size)
        for r in reconstructions
    ]
    fn_blocks = [s.notes if s else None for s in splits]
    cut = sum(1 for s in splits if s)
    if cut:
        print(f"Footnote blocks cut by type size: {cut} pages", file=sys.stderr)
    page_lines = [s.body if s else r.lines for s, r in zip(splits, reconstructions)]
    # Left edges, kept parallel to page_lines: the peeled label tail behind a
    # footnote cut carries none.
    page_indents = [
        (r.indents[: s.split_at] + [None] * (len(s.body) - s.split_at))
        if s
        else list(r.indents)
        for s, r in zip(splits, reconstructions)
    ]
    page_sizes = [
        (r.sizes[: s.split_at] + [None] * (len(s.body) - s.split_at))
        if s
        else list(r.sizes)
        for s, r in zip(splits, reconstructions)
    ]

    # Run-in headings, cut off the paragraph they open. The emphasis is measured
    # on the printed line, so this has to happen while lines, sizes and edges are
    # still parallel — afterwards the heading is an ordinary numbered line and
    # ``heading_level`` reads it like any other.
    from scriptor.reflow.headings import split_emphasised_headings

    page_emphases = [
        (r.emphases[: s.split_at] + [0] * (len(s.body) - s.split_at))
        if s
        else list(r.emphases)
        for s, r in zip(splits, reconstructions)
    ]
    cut_headings = 0
    new_lines, new_sizes, new_indents = [], [], []
    for lines, emph, sizes, indents in zip(
        page_lines, page_emphases, page_sizes, page_indents
    ):
        result = split_emphasised_headings(
            # The type size only opens a heading where the document is set in
            # columns. It is calibrated on articles, where "Abstract" is bold at
            # 10.91pt over a 9.06pt body; an OCR layer reports size and weight
            # too loosely for it — Zuckerman's front matter turns "Jan" into a
            # chapter. Numbered headings are unaffected and keep working there.
            lines, emph, sizes, indents,
            body_size=doc_body_size if gutter is not None else None,
        )
        cut_headings += len(result[0]) - len(lines)
        new_lines.append(result[0])
        new_sizes.append(result[1])
        new_indents.append(result[2])
    page_lines, page_sizes, page_indents = new_lines, new_sizes, new_indents
    if cut_headings:
        print(
            f"Run-in headings separated from their paragraph: {cut_headings}",
            file=sys.stderr,
        )

    # A bibliography is set with a hanging indent — the entry at the column edge,
    # its continuations indented — which is the paragraph indent read backwards.
    # Joining the entries here, while lines, sizes and edges are still parallel,
    # keeps both the indent rule and the short-line rule off them.
    from scriptor.reflow.references import merge_reference_entries

    joined = merge_reference_entries(
        list(zip(page_lines, page_sizes, page_indents)), body_size=doc_body_size
    )
    entries = sum(
        1
        for (before, _s, _i), (after, _s2, _i2) in zip(
            zip(page_lines, page_sizes, page_indents), joined
        )
        for _ in range(len(before) - len(after))
    )
    if entries:
        print(
            f"Reference list: {plural(entries, 'line')} joined into their entries",
            file=sys.stderr,
        )
    page_lines = [lines for lines, _s, _i in joined]
    page_indents = [indents for _l, _s, indents in joined]

    # The catalogue's outline, believed entry by entry where the page confirms
    # the title: the confirmed chapter starts become headings, and the chapter
    # titles inform running-head removal — the generic stripper below would
    # preserve the title's own year ("… in 759") as a phantom folio.
    from scriptor.reflow import outline as outline_mod
    entries = outline_mod.load_outline(src)
    pos_by_phys = {sp.index: pos for pos, sp in enumerate(source_pages)}
    headings_by_pos: dict[int, str] = {}
    if entries and outline_mod.credible(entries):
        level1 = [e for e in entries if e.level == 1]
        positional = [
            outline_mod.OutlineEntry(e.level, e.title, pos_by_phys[e.page] + 1)
            for e in level1
            if e.page in pos_by_phys
        ]
        confirmed = outline_mod.chapter_headings(positional, page_lines)
        for page_no, (title, k) in confirmed.items():
            page_lines[page_no - 1] = page_lines[page_no - 1][k:]
            page_indents[page_no - 1] = page_indents[page_no - 1][k:]
            headings_by_pos[page_no - 1] = title
        chapter_titles = [t for t, _k in confirmed.values()]
        print(
            f"Outline: {len(confirmed)} of {len(level1)} level-1 entries "
            f"confirmed as chapter starts",
            file=sys.stderr,
        )
    else:
        chapter_titles = []

    # A first-line indent is the typographic paragraph signal — it catches the
    # paragraph ends the short-line heuristic misses (a last line set at full
    # width). Injected as blank lines, which parse_page/merge already read as
    # paragraph breaks. This is the last consumer of the indent column, so it
    # runs before anything edits lines out from under it; from here on the
    # lines carry their own structure.
    from scriptor.reflow.textlines import mark_indent_breaks
    page_lines = [
        mark_indent_breaks(lines, indents)
        for lines, indents in zip(page_lines, page_indents)
    ]

    # Chapter running heads, removed with knowledge of the full title — the
    # generic stripper below would preserve the title's own year ("… in 759")
    # as a phantom folio.
    if chapter_titles:
        page_lines = outline_mod.strip_running_titles(page_lines, chapter_titles)

    raw_texts = ["\n".join(lines) for lines in page_lines]

    # Remove running heads and footers document-wide, before parse_page runs.
    from scriptor.reflow.running_elements import strip_running_elements
    cleaned, headers, footers = strip_running_elements(raw_texts)
    if headers:
        print(f"Running headers removed ({len(headers)}): {headers[:3]}", file=sys.stderr)
    if footers:
        print(f"Running footers removed ({len(footers)}): {footers[:3]}", file=sys.stderr)

    pages: list[Page] = []
    for ordinal, (text, fn_block, sp, rec) in enumerate(
        zip(cleaned, fn_blocks, source_pages, reconstructions), start=1
    ):
        pg = parse_page(text, fn_block=fn_block, geometry_verified=rec.measured)
        if pg is not None:
            pg.backend_label = sp.label
            pg.heading = headings_by_pos.get(ordinal - 1)
            # The physical page, counted over the source files. Always known,
            # even where nothing is printed on the page. Kept as the counterpart
            # to page_label/page_number in the archilles chunk schema; not
            # emitted yet, because the marker syntax for it is a decision shared
            # with that repo (see docs/.../2026-07-08-page-label-modell-design.md).
            pg.index = ordinal
            pages.append(pg)

    reattached = attach_continuations(pages)
    if reattached:
        print(
            f"Footnote continuations reattached across page breaks: {reattached}",
            file=sys.stderr,
        )

    page_col = reconcile_page_numbers(pages)
    print(f"Page label position: {page_col}", file=sys.stderr)

    assign_modes(pages)
    mode_counts = Counter(p.mode for p in pages)
    print(f"Mode distribution: {dict(mode_counts)}", file=sys.stderr)

    threshold, hist = calibrate_threshold(pages)
    print(f"Calibration (main pages only): threshold <= {threshold} chars", file=sys.stderr)
    print(f"  Most common line lengths: {hist.most_common(5)}", file=sys.stderr)

    # Counted once, used by both renders and by the decision applier. If the two
    # renders disagreed on the ranking, "cand 1" in the decision file would mean
    # one glyph while writing it and another while reading it back.
    evidence = document_evidence(pages, threshold, ocr_profile)
    known = {d for d, _g in evidence.counts} | {d for d, _g in evidence.pseudo}
    for digit in sorted(known):
        if not evidence.informed(digit):
            continue
        glyphs = sorted(
            evidence.glyphs_for(digit), key=lambda g: -evidence.share(digit, g)
        )
        shown = ", ".join(
            f"{g!r} {evidence.count(digit, g)}x ({evidence.share(digit, g):.0%})"
            for g in glyphs
        )
        source = " (profile)" if evidence.from_profile(digit) else ""
        print(f"Glyph evidence for footnote {digit}{source}: {shown}", file=sys.stderr)

    decisions.reset_report()
    clean_output, _ = render_book(
        pages, threshold, fmt, decisions=decisions, evidence=evidence
    )
    Path(out_path).write_text(clean_output, encoding="utf-8")
    print(f"Written: {out_path}", file=sys.stderr)

    if decisions.accepted:
        print(
            f"Decisions: {plural(len(decisions.applied), 'marker')} placed",
            file=sys.stderr,
        )
    for page, fn in decisions.unmatched:
        print(
            f"  ! decision for footnote {fn} on page {page} matched no candidate "
            f"and was ignored",
            file=sys.stderr,
        )

    # Annotated master (always, option 3) — second render pass with the annotator.
    from scriptor.reflow.confidence import Annotator
    annotator = Annotator()
    decisions.reset_report()   # the clean render already reported; do not double count
    review_output, _ = render_book(
        pages, threshold, fmt, annotator=annotator, decisions=decisions, evidence=evidence
    )
    op = Path(out_path)
    review_path = op.with_name(f"{op.stem}.review{op.suffix}")
    review_path.write_text(review_output, encoding="utf-8")
    print(
        f"Annotated master: {review_path}  "
        f"({plural(len(annotator.annotations), 'uncertain footnote')})",
        file=sys.stderr,
    )

    # Extended audit sidecar built from the annotations + run summary.
    from scriptor.reflow.confidence import render_audit
    total_fn_defs = sum(len(p.footnotes) for p in pages)
    audit_text = render_audit(
        annotator.annotations, total_fn_defs, len(pages), out_path
    )
    audit_path = op.with_suffix(op.suffix + ".audit.txt")
    audit_path.write_text(audit_text, encoding="utf-8")
    print(
        f"Audit: {plural(len(annotator.annotations), 'uncertain footnote')} -> {audit_path}",
        file=sys.stderr,
    )

    # Decision sidecar: the still-open choices, ready to be marked. Regenerated
    # every run, so it shrinks as decisions are made and applied.
    decisions_out = op.with_name(op.name + ".decisions.txt")
    decisions_out.write_text(
        decisions_mod.render_template(
            annotator.annotations, out_path, str(decisions_out)
        ),
        encoding="utf-8",
    )
    open_count = sum(len(a.candidates) for a in annotator.annotations if a.page)
    print(
        f"Decisions open: {plural(open_count, 'candidate')} -> {decisions_out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    fmt = None
    if "--format" in args:
        i = args.index("--format")
        fmt = args[i + 1]
        del args[i : i + 2]
    if len(args) >= 2:
        main(args[0], args[1], fmt)
    else:
        main(".", "Staufer_und_Welfen_reflow.txt", fmt)
