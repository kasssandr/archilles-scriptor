"""Running-header and running-footer detection.

Adapted from ``archilles/src/extractors/pdf_extractor.py`` (methods
``_detect_running_headers`` / ``_detect_running_footers`` and helpers).
Refactored from PDFExtractor methods into module-level functions that
operate on a list of plain page texts, so they can be called from
``scriptor``'s pipeline without pulling in the Archilles class hierarchy.

Used after extraction but before ``parse_page`` — we strip the repeating
running head from each raw page text so the reflow stage sees only
body + footnotes.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from scriptor.reflow.headings import MARK
from scriptor.reflow.heads import HeadCandidates, without_edge_number
from scriptor.reflow.outline import KnownTitles
from scriptor.reflow.rescued import RescuedFolios


def _strings_are_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # A running element quoted inside a much longer line is body text, not a
    # running element. The containment shortcut may therefore only fire when b
    # makes up essentially all of a — otherwise a footnote citing the publisher
    # whose name is the running footer loses its whole line (EXCITE 35056 p. 4:
    # "Bonn: Deutsches Institut für Entwicklungspolitik (Discussion Paper
    # 7/2006)." vs. the footer "Deutsches Institut für Entwicklungspolitik").
    if b in a and len(b) >= threshold * len(a):
        return True
    # ``ratio`` walks the two strings looking for matching blocks and is by far
    # the most expensive thing this module does. ``real_quick_ratio`` (lengths
    # alone) and ``quick_ratio`` (a multiset count of the characters) are exact
    # upper bounds on it, so a pair either bound already rules out cannot become
    # similar by looking closer -- skipping the walk there changes no answer,
    # only the bill. This is difflib's own idiom (``get_close_matches``).
    #
    # It matters where the grouping loop grows: a volume whose pages begin
    # mid-sentence puts nearly every first line in a group of its own, and each
    # new line is then compared against all of them. The Oxford Handbook (911
    # pages, no repeating head over most of the volume) spent 98.5 % of an
    # 18-minute run in here. Measured on 400 unrelated lines: 16.2s -> 3.3s.
    # The gain is larger on real prose than on this synthetic case, where every
    # line draws from one small word pool and ``quick_ratio`` (which counts
    # characters, not order) therefore clears the threshold more often than it
    # would on text.
    matcher = SequenceMatcher(None, a.lower(), b.lower())
    return (matcher.real_quick_ratio() >= threshold
            and matcher.quick_ratio() >= threshold
            and matcher.ratio() >= threshold)


def _normalize_header_line(line: str) -> str:
    normalized = " ".join(line.split())
    normalized = re.sub(r"^\d+\s*", "", normalized)
    normalized = re.sub(r"\s*\d+$", "", normalized)
    return normalized


# When a running header/footer is stripped, an edge page number embedded in it
# ("146 WILHELM HEIL" / "WILHELM HEIL 147") must survive the strip. It is handed
# back to the caller as a *rescued* number, never written back into the text:
# the line was furniture, and a bare number put back in its place is
# indistinguishable from a folio the page prints in its own right. Rescued, it
# travels to the consensus with its own weight and its own reason. We never
# invent one. This mirrors the leading/trailing-digit handling in
# _normalize_header_line: the module already treats an edge digit-run in a
# running element as a page number.
_LEAD_PAGE_NUM = re.compile(r"^(\d{1,4})\s+\S")
_TRAIL_PAGE_NUM = re.compile(r"\S\s+(\d{1,4})$")


def _extract_edge_page_number(line: str) -> str | None:
    """Return the leading/trailing page-number digits of a header/footer line,
    or None if the line carries no edge number."""
    s = line.strip()
    m = _LEAD_PAGE_NUM.match(s)
    if m:
        return m.group(1)
    m = _TRAIL_PAGE_NUM.search(s)
    if m:
        return m.group(1)
    return None


# A number at the edge of a head line is a folio where it counts the pages
# between two of its lines. Meisel, *Der Mythus der herrschenden Klasse*, opens
# each chapter "1. Kapitel", "2. Kapitel", … some twenty pages apart; *De
# eerste minister* each "Hoofdstuk 1", "Hoofdstuk 2", …. Such a wording never
# runs, and a head that never runs is left standing -- but only where no
# number stands on it that the consensus would miss, and these lines carry one
# on every page. One up in twenty pages counts nothing. The period an ordinal
# carries is allowed for here; the folio rules never read "1." as a number.
_LEAD_NUMBER = re.compile(r"^(\d{1,4})\.?\s+\S")
_TRAIL_NUMBER = re.compile(r"\S\s+(\d{1,4})\.?$")
# How far the number may run from the page count and still be counting it:
# one scan image per two-page spread doubles it (Les apologistes grecs), a
# plate or a lost blank page shifts it.
_FOLIO_RATE = (0.5, 2.5)


def _numbers_count_no_pages(members: list[tuple[int, str]]) -> bool:
    """Whether the numbers a wording carries at its edges are the text's own:
    one edge numbered on at least two lines, and at no edge does the number
    count the pages from one numbered line to the next in at least half the
    steps. ``members`` are (page index, line), in page order."""
    numbered = False
    for edge in (_LEAD_NUMBER, _TRAIL_NUMBER):
        found = [(i, int(m.group(1))) for i, line in members
                 if (m := edge.search(line.strip()))]
        if len(found) < 2:
            continue
        numbered = True
        steps = list(zip(found, found[1:]))
        counting = sum(1 for (i, u), (j, v) in steps
                       if j > i and _FOLIO_RATE[0] <= (v - u) / (j - i) <= _FOLIO_RATE[1])
        if counting * 2 >= len(steps):
            return False
    return numbered


def _below_head(pages_text: list[str]) -> list[tuple[int, str]]:
    """(page index, normalized line) of every line under a page's head region,
    the head region counted as ``detect_running_headers`` counts it."""
    out = []
    for index, page_text in enumerate(pages_text):
        lines_checked = 0
        for line in page_text.strip().split("\n"):
            if not line.strip():
                continue
            if lines_checked < 3:
                lines_checked += 1
                continue
            normalized = _normalize_header_line(line)
            if normalized and len(normalized) > 5:
                out.append((index, normalized))
    return out


def _printed_in_body(
    wording: str,
    heads_at: set[int],
    below: list[tuple[int, str]],
    similarity_threshold: float,
) -> bool:
    """Whether the volume prints this wording under the head region of at
    least as many pages as it heads. A running head stands at the head of its
    pages, and at most once more where its section opens in mid-page. Meisel's
    endnotes print "28 A. a. O., S. 292." and "Zum 12. Kapitel" at the top of
    a few pages because a note happens to begin there -- and dozens of times
    lower down, where the stripper never looked."""
    width = len(wording)
    pages: set[int] = set()
    for index, normalized in below:
        # The bound ``real_quick_ratio`` would compute, without building the
        # matcher: most lines of prose are far longer than a running head.
        if 2 * min(width, len(normalized)) < similarity_threshold * (width + len(normalized)):
            continue
        if index not in pages and _strings_are_similar(normalized, wording, similarity_threshold):
            pages.add(index)
            if len(pages) >= len(heads_at):
                return True
    return False


def detect_running_headers(
    pages_text: list[str],
    min_occurrences: int = 3,
    similarity_threshold: float = 0.85,
) -> list[str]:
    if len(pages_text) < min_occurrences:
        return []

    first_lines: list[tuple[int, str, str]] = []
    for index, page_text in enumerate(pages_text):
        lines_checked = 0
        for line in page_text.strip().split("\n"):
            if lines_checked >= 3:
                break
            if not line.strip():
                continue
            lines_checked += 1
            normalized = _normalize_header_line(line)
            if normalized and len(normalized) > 5:
                first_lines.append((index, line, normalized))

    groups: list[list] = []  # [canonical, count, [(page index, line)]]
    for index, line, normalized in first_lines:
        matched = False
        for g in groups:
            if _strings_are_similar(normalized, g[0], similarity_threshold):
                if len(normalized) > len(g[0]):
                    g[0] = normalized
                g[1] += 1
                g[2].append((index, line))
                matched = True
                break
        if not matched:
            groups.append([normalized, 1, [(index, line)]])

    frequent = [g for g in groups if g[1] >= min_occurrences]
    below = _below_head(pages_text) if frequent else []
    return [g[0] for g in frequent
            if not _printed_in_body(g[0], {i for i, _line in g[2]}, below,
                                    similarity_threshold)]


def header_of_page(
    page_text: str,
    running_headers: list[str],
    similarity_threshold: float = 0.85,
) -> str | None:
    """The running header this page carries, in its canonical form.

    Same matching rule as ``remove_running_headers`` below, exposed on its own
    because the header says more than that it is repeated furniture: a page
    headed *Selected Bibliography* announces its region on every page of it
    (PREPARED_FORMAT_SPEC §4.4). Stripping used to be the only thing that
    happened to that knowledge.
    """
    lines_checked = 0
    for line in page_text.strip().split("\n"):
        if not line.strip():
            continue
        if lines_checked >= 3:
            break
        normalized = _normalize_header_line(line)
        if not normalized:
            continue
        lines_checked += 1
        for header in running_headers:
            if _strings_are_similar(normalized, header, similarity_threshold):
                return header
    return None


# How far back a page looks for the running head it carries before it counts as
# opening that head's run. Two covers a volume that sets the section title on
# the rectos only; three forgives one page where the OCR lost the head.
_OPENING_LOOKBACK = 3
# A page this short before an opening is a section's last page or a part
# title, not a page whose text runs on.
_SHORT_PAGE = 6
# How often one head may open a run before it counts as the volume's own.
_MAX_OPENINGS = 2
_BARE_FOLIO = re.compile(r"^\d{1,4}$")
_SENTENCE_END = re.compile(r"[.!?…][\"'»«“”‘’)\]]*$")
_MANGLED_EDGE = re.compile(r"^(?=\S{0,4}\d)\S{1,5}\s|\s(?=\S{0,4}\d)\S{1,5}$")
_MANGLED_ALONE = re.compile(r"^(?=\S{0,4}\d)\S{1,5}$")
_ROMAN_EDGE = re.compile(r"^([IVXLCDM]{1,7}|[ivxlcdm]{1,7})\s|\s([IVXLCDM]{1,7}|[ivxlcdm]{1,7})$")


def _head_lines(page_text: str) -> list[tuple[int, str]]:
    """(index, line) of the first three lines with words, as the strippers
    count, together with any bare number standing among or next to them."""
    out = []
    words = 0
    for k, line in enumerate(page_text.strip().split("\n")):
        if not line.strip():
            continue
        if _normalize_header_line(line):
            if words >= 3:
                break
            words += 1
        out.append((k, line))
    return out


def _foliated(head: list[tuple[int, str]], furniture: set[int]) -> bool:
    """Whether a folio stands in the head region: a bare number, or one at
    the edge of a running head (``furniture``, positions in ``head``). A
    number closing a line of prose is the prose's own -- Taubes p. 7 opens
    its introduction with "… reichen von 1953".

    The OCR's mangled folios count too, standing alone or at the edge of a
    running head ("I99", "A56", "•324", "8?" in L'Empire chrétien and the
    Chaldaean Oracles): a short token with a digit in it is no word of a
    title. Alone on its line, "8?" had become the first half of a title
    "set over two lines".
    Roman numerals are not judged here: "XIV THE BYZANTINE INHERITANCE IN
    RUSSIA" is Baynes's chapter, not its page. ``opening_pages`` tells the
    two apart over the run."""
    return any(_BARE_FOLIO.match(line.strip())
               or _MANGLED_ALONE.match(line.strip())
               or (at in furniture and (_extract_edge_page_number(line)
                                        or _MANGLED_EDGE.search(line.strip())))
               for at, (_k, line) in enumerate(head))


_URL = re.compile(r"https?://|www\.|doi\.org", re.I)


def _could_head(line: str) -> bool:
    """Whether a line is printed text rather than a producer's stamp. A
    download banner on each chapter's first page never runs either -- the
    Oxford Handbook prints "The Oxford Handbook of … Rubina Raja (ed.)
    https://…" over 51 of them -- and it is furniture all the same. No limit
    on length: mehr-themistios titles its chapters "III Die or. 6: Die
    Nachahmung des Göttlichen des von Gott auf die Erde geschickten Kaisers"."""
    return not _URL.search(line)


def _in_body(page_text: str, header: str, similarity_threshold: float) -> bool:
    """Whether the page prints this wording below its head region: there a
    section opens in mid-page, and its running head starts a page later."""
    lines = page_text.strip().split("\n")
    head = _head_lines(page_text)
    start = head[-1][0] + 1 if head else 0
    return any(_strings_are_similar(n, header, similarity_threshold)
               for n in map(_normalize_header_line, lines[start:]) if n)


def _ends_a_text(page_text: str) -> bool:
    """Whether the text before an opening may stop here: nothing on the page,
    a page too short to be running prose, or a last line closing a sentence.
    A bare number at the foot is the folio and is looked past."""
    lines = [ln.strip() for ln in page_text.strip().split("\n") if ln.strip()]
    while lines and _BARE_FOLIO.match(lines[-1]):
        lines.pop()
    return len(lines) <= _SHORT_PAGE or bool(_SENTENCE_END.search(lines[-1]))


def _canonical(running_headers: list[str], similarity_threshold: float) -> dict[str, str]:
    """{detected head: the first detected head it reads as}.

    The detector groups each wording against the longest so far, so one
    head the OCR spells three ways can come out as three groups (La
    masonería: "TII. Más ALLÁ DEL MITO DE HIRAM", "MI. Más …", "TI. Más …
    HikaM"). Counted apart, the opening's head has no run after it.
    """
    canon: dict[str, str] = {}
    for header in running_headers:
        canon[header] = next(
            (c for c in dict.fromkeys(canon.values())
             if _strings_are_similar(header, c, similarity_threshold)), header)
    return canon


def opening_pages(
    pages_text: list[str],
    running_headers: list[str],
    similarity_threshold: float = 0.85,
    lists: frozenset[int] | set[int] = frozenset(),
    carried_out: list[set[str]] | None = None,
) -> dict[int, dict[int, list[int]]]:
    """{page index: {first line: the lines that spell the title}} for each
    page that opens a running head's run; line indices count in
    ``page_text.strip().split("\\n")``, as the strippers do.

    A section's title and its running head print the same words, and the
    page that opens the section carries them in its head region like every
    page after it. Without a list of the volume's titles to recognise it by
    (``known``), the stripper took the title with the furniture: Taubes, *Vom
    Kult zur Kultur*, lost all twenty-five essay titles and its introduction's
    heading that way, its contents being unreadable to the parser.

    The page that opens a run says so itself, on five counts, all required:

    * none of the ``_OPENING_LOOKBACK`` pages before it carries this head,
      and one of as many after it does -- a run is a run; a sentence that
      happens to recur through the volume opens nothing. Nor do those pages
      print the wording in their text: a section that opens in mid-page has
      its heading there, and its running head begins on the next page (Gli
      Actus p. XIX, L'Empire chrétien p. 87);
    * no folio stands in its head region -- an opening page prints its number
      at the foot or not at all, a running page with its head. A page that
      carries the furniture of a running page is one, whatever else recurs
      on it;
    * the wording does not stand again lower on the page: there the heading
      is that line, and the head-region one is furniture set from the state
      at the page's end (Bauer p. 23, "B. Gang der Darstellung");
    * the text before it ends: the page before is empty, short, or closes a
      sentence. Many volumes print no running head on a chapter's first page,
      and their run then begins on the second, in mid-sentence.

    A head that passes all five on more than ``_MAX_OPENINGS`` pages opens
    none of them: it is the volume's furniture, pausing at chapter openings.

    ``lists`` are the volume's contents pages: every title stands there, and
    one standing two pages before the introduction does not make the
    introduction's own opening a running page.

    ``carried_out``, where given, receives per page the running heads it
    carries in its head region.

    A title the opening sets over two lines is one title: the running head
    repeats it on one ("Nachman Krochmal und der moderne" / "Historismus"
    under "Nachman Krochmal und der moderne Historismus"). The stripper never
    deleted those -- neither line alone is the head -- but they ran into the
    paragraph below as text.
    """
    canon = _canonical(running_headers, similarity_threshold)

    def head_of(normalized: str) -> str | None:
        return next((canon[h] for h in running_headers
                     if _strings_are_similar(normalized, h, similarity_threshold)),
                    None)

    carried: list[set[str]] = []
    seen: list[tuple[list[tuple[int, str]], set[int], list[tuple[list[int], str]]]] = []
    for index, page_text in enumerate(pages_text):
        here: set[str] = set()
        head = _head_lines(page_text)
        words = [at for at, (_k, line) in enumerate(head)
                 if _normalize_header_line(line)]
        if index in lists:
            words = []
        taken: set[int] = set()
        spans: list[tuple[list[int], str]] = []
        for at in words:
            if at in taken:
                continue
            header = head_of(_normalize_header_line(head[at][1]))
            span = [at]
            if header is None and at + 1 in words:
                header = head_of(_normalize_header_line(
                    f"{head[at][1].strip()} {head[at + 1][1].strip()}"))
                span = [at, at + 1]
            if header is None:
                continue
            taken.update(span)
            here.add(header)
            spans.append((span, header))
        carried.append(here)
        seen.append((head, taken, spans))
    if carried_out is not None:
        carried_out.extend(carried)

    # A roman numeral at the edge of a running head is its folio where it
    # changes from page to page (Gli Actus: "LE DIREZIONI DELLA RICERCA XIX",
    # "… XXI"), and the section's number where it stays (Baynes: "XIV THE
    # BYZANTINE INHERITANCE IN RUSSIA" over the whole chapter).
    # Within a run, that is: L'Empire chrétien heads each chapter's first page
    # "CHAPITRE III", "CHAPITRE IV", …, one wording to the detector, and the
    # numeral changes from chapter to chapter, never from page to page.
    romans: dict[str, list[tuple[int, str]]] = {}
    for index, (head, _taken, spans) in enumerate(seen):
        for span, header in spans:
            m = len(span) == 1 and _ROMAN_EDGE.search(head[span[0]][1].strip())
            if m:
                romans.setdefault(header, []).append((index, m.group(1) or m.group(2)))
    # A folio changes at nearly every step, a chapter's number only where the
    # next chapter begins (Chaldaean Oracles: "CHAPTER IV" two pages before
    # "CHAPTER V"). The majority of the near pairs decides.
    paged = set()
    for header, values in romans.items():
        near = [u != v for (i, u), (j, v) in zip(values, values[1:])
                if j - i <= _OPENING_LOOKBACK]
        if near and sum(near) * 2 > len(near):
            paged.add(header)

    # Where the numeral is the section's, it is part of what the head says:
    # "CHAPTER IV" and "CHAPTER V" are two heads to everything below, though
    # one wording to the detector.
    # Only where one line alone is the head: a title joined from two lines
    # takes its numeral from the line above the head's words (La masonería:
    # "CAPÍTULO III" / "MÁS ALLÁ DEL MITO DE HIRAM", then pages headed by the
    # wording alone).
    def key(head, span, header) -> tuple[str, str]:
        if header in paged or len(span) > 1:
            return header, ""
        m = _ROMAN_EDGE.search(head[span[0]][1].strip())
        return header, (m.group(1) or m.group(2)) if m else ""

    keyed: list[set[tuple[str, str]]] = [
        {key(head, span, header) for span, header in spans}
        for head, _taken, spans in seen]
    heads_at: list[list[tuple[list[int], tuple[str, str]]]] = []
    for head, taken, spans in seen:
        roman_folio = any(header in paged and len(span) == 1
                          and _ROMAN_EDGE.search(head[span[0]][1].strip())
                          for span, header in spans)
        heads_at.append(
            [] if roman_folio or _foliated(head, taken)
            else [([head[a][0] for a in span], key(head, span, header))
                  for span, header in spans])

    openings: dict[int, dict[int, list[int]]] = {}
    opened: dict[tuple[str, str], int] = {}
    spoken: dict[tuple[int, int], tuple[str, str]] = {}
    for index, found in enumerate(heads_at):
        if not found or index == 0:
            continue
        if not _ends_a_text(pages_text[index - 1]):
            continue
        head = _head_lines(pages_text[index])
        lines = pages_text[index].strip().split("\n")
        below = [_normalize_header_line(ln) for ln in lines[head[-1][0] + 1:]]
        for span, k in found:
            header = k[0]
            if any(k in keyed[j]
                   for j in range(max(0, index - _OPENING_LOOKBACK), index)):
                continue
            if not any(k in keyed[j] for j in range(
                    index + 1, min(len(keyed), index + 1 + _OPENING_LOOKBACK))):
                continue
            if any(_in_body(pages_text[j], header, similarity_threshold)
                   for j in range(max(0, index - _OPENING_LOOKBACK), index)):
                continue
            if any(_strings_are_similar(b, header, similarity_threshold)
                   for b in below if b):
                continue
            openings.setdefault(index, {})[span[0]] = span
            opened[k] = opened.get(k, 0) + 1
            spoken[(index, span[0])] = k

    # A head that opens again and again is the volume's, not a section's:
    # the book title over every verso pauses at each chapter's first page and
    # resumes on its second (La masonería). A section opens once -- twice
    # where its title also stands on the title page.
    for (index, first), k in spoken.items():
        if opened[k] > _MAX_OPENINGS:
            del openings[index][first]
            if not openings[index]:
                del openings[index]
    return openings


def remove_running_headers(
    pages_text: list[str],
    running_headers: list[str],
    rescued: RescuedFolios,
    similarity_threshold: float = 0.85,
    known: KnownTitles | None = None,
    heads: HeadCandidates | None = None,
    lists: frozenset[int] | set[int] = frozenset(),
    kept: list[tuple[int, str]] | None = None,
) -> list[str]:
    """Strip the running head, adding the folios that shared its lines to
    ``rescued``.

    Every number is added, not just the first: a page can carry more than one
    line of furniture and they do not say the same thing. Josephus and Jesus
    heads its pages twice, with a download banner ending in the year 2025 and
    with the chapter's running head ending in the folio; keeping only the first
    threw the folio away and left the year to speak for the page.

    ``known`` are the titles the volume's own lists name. *Every* head-region
    line is asked, not only the ones this stripper would have deleted: Bauer
    prints "B. Gang der Darstellung" over page 23 and again in the middle of
    it, and the wording occurs twice in the volume, one short of the three
    repetitions that make a running head. The line stayed, and the word it
    broke ("kommunika|tive") stayed broken. Such a line is recorded in
    ``heads`` and the placement decides (Gliederungsmodell §5.2, rule 6).
    Without both arguments the stripper deletes as it always did.

    ``lists`` are the pages of the volume's own contents (0-based). Nothing at
    the head of those is text this stripper may take: the first line of Bauer's
    contents is its own heading, and the second is the entry
    "Abbildungsverzeichnis 17", which reads as the running head of the list of
    figures eight pages on. Stripping there cost the contents its heading and
    an entry its page number. The line stays whole -- with its number, which
    belongs to the entry -- and is still handed to the consensus as a rescued
    folio, because what the pagination was told must not change with this.

    A head line on the page that opens its head's run (``opening_pages``)
    stays as text: it is the section's title, and the volume names it
    nowhere this stripper can see. ``known`` is asked first; what it
    recognises goes to the placement as before. Each line kept this way is
    noted in ``kept`` as (page index, line). A wording the detector grouped
    but that never stands at the head of two pages near each other is no
    running head at all, and stays as text wherever it carries no number.
    """
    carried: list[set[str]] = []
    openings = opening_pages(pages_text, running_headers, similarity_threshold,
                             lists, carried)
    # A wording that recurs at the head of pages but never on two near each
    # other is no running head: furniture runs. L'Empire chrétien prints
    # "CHAPITRE III", "CHAPITRE IV", … over each chapter's first page alone,
    # one wording to the detector, and lost the first line of every chapter.
    at_pages: dict[str, list[int]] = {}
    for i, here in enumerate(carried):
        for header in here:
            at_pages.setdefault(header, []).append(i)
    runless = {header for header, idx in at_pages.items()
               if all(j - i > _OPENING_LOOKBACK for i, j in zip(idx, idx[1:]))}
    canon = _canonical(running_headers, similarity_threshold)
    # Of those, the ones whose numbers are their own (``_numbers_count_no_pages``):
    # "1. Kapitel" stays with its number, which is no folio.
    own_numbers = {
        header for header in runless
        if _numbers_count_no_pages([
            (i, line) for i in at_pages[header]
            for _k, line in _head_lines(pages_text[i])
            if any(canon.get(h) == header
                   and _strings_are_similar(_normalize_header_line(line), h,
                                            similarity_threshold)
                   for h in running_headers)])}
    cleaned_pages = []
    for index, page_text in enumerate(pages_text):
        a_list = index in lists
        lines = page_text.strip().split("\n")
        cleaned_lines: list[str] = []
        lines_checked = 0
        opening = openings.get(index, {})
        joined: set[int] = set()
        # Where the head region carries a title the volume names, the
        # placement decides about that page, and a line left standing above
        # the title shifts what it reads as the head region: L'Empire chrétien
        # p. 53 lost "A CONSTANTINOPLE" as a heading under "CHAPITRE II".
        placed_here = (known is not None and heads is not None and any(
            known.of(line) for _k, line in _head_lines(page_text)))
        for k, line in enumerate(lines):
            if not line.strip():
                cleaned_lines.append(line)
                continue
            normalized = _normalize_header_line(line)
            in_head = lines_checked < 3 and bool(normalized)
            if k in joined:
                # The second line of an opening title, written with the first.
                lines_checked += in_head
                continue
            is_header = False
            matched = None
            if in_head:
                lines_checked += 1
                for header in running_headers:
                    if _strings_are_similar(normalized, header, similarity_threshold):
                        is_header = True
                        matched = header
                        break
            title = (known.of(line)
                     if in_head and known is not None and heads is not None
                     else None)
            if a_list and is_header and heads is not None:
                # On a contents page the deletion waits, and the line waits
                # whole: its number is the entry's page, not the page's folio.
                rescued.add(index, "top", _extract_edge_page_number(line))
                heads.add(index, len(cleaned_lines), line, title or line.strip())
                cleaned_lines.append(line)
                continue
            if title is not None:
                # A title the volume names is not this stripper's to decide
                # about, whether or not the wording repeats often enough to be
                # read as furniture: on the page that opens the section it is
                # the heading, and three occurrences elsewhere say nothing
                # about this one. Where the stripper *had* judged it -- the
                # wording matched a detected head -- the folio it carried is
                # rescued and taken off the line, as it always was, so that
                # the page is not read as printing that number twice.
                folio = _extract_edge_page_number(line) if is_header else None
                if is_header:
                    rescued.add(index, "top", folio)
                stays = without_edge_number(line, folio) if is_header else line
                heads.add(index, len(cleaned_lines), stays, title, is_header)
                cleaned_lines.append(stays)
                continue
            span = opening.get(k)
            if span is not None:
                text = " ".join(lines[j].strip() for j in span)
                if known is None or heads is None or known.of(text) is None:
                    # The opening page's title, marked as set apart: left as
                    # plain text it would run into the paragraph below it. No
                    # folio stands with it (opening_pages requires none), so
                    # nothing is rescued.
                    if kept is not None:
                        kept.append((index, text))
                    cleaned_lines.append(MARK + text)
                    joined.update(span[1:])
                    continue
            if not is_header:
                cleaned_lines.append(line)
                continue
            if (canon.get(matched) in runless and not a_list and not placed_here
                    and _could_head(line)
                    and (canon.get(matched) in own_numbers
                         or (not _extract_edge_page_number(line)
                             and not _MANGLED_EDGE.search(line.strip())))
                    and not _foliated(_head_lines(page_text), set())):
                # Not furniture (see ``runless``), and no number on it or near
                # it that the consensus would miss: left standing above a bare
                # folio, the line would push it off the first line, where
                # parse_page reads it (Chaldaean Oracles p. 222, printed ->
                # computed). A number the wording carries as its own is not one
                # the consensus misses. The line stays as the page printed it.
                cleaned_lines.append(line)
                continue
            # The title goes, and so does the number's place in the text;
            # the number itself is handed on as a witness.
            rescued.add(index, "top", _extract_edge_page_number(line))
        cleaned_pages.append("\n".join(cleaned_lines))
    return cleaned_pages


def detect_running_footers(
    pages_text: list[str],
    min_occurrences: int | None = None,
    similarity_threshold: float = 0.85,
) -> list[str]:
    if min_occurrences is None:
        min_occurrences = max(10, len(pages_text) // 20)
    if len(pages_text) < min_occurrences:
        return []

    last_lines: list[str] = []
    for page_text in pages_text:
        lines = page_text.strip().split("\n")
        lines_checked = 0
        for line in reversed(lines):
            if lines_checked >= 3:
                break
            if not line.strip():
                continue
            lines_checked += 1
            normalized = _normalize_header_line(line)
            if normalized and len(normalized) > 5:
                last_lines.append(normalized)

    groups: list[list] = []
    for normalized in last_lines:
        matched = False
        for g in groups:
            if _strings_are_similar(normalized, g[0], similarity_threshold):
                if len(normalized) > len(g[0]):
                    g[0] = normalized
                g[1] += 1
                matched = True
                break
        if not matched:
            groups.append([normalized, 1])

    return [g[0] for g in groups if g[1] >= min_occurrences]


def remove_running_footers(
    pages_text: list[str],
    running_footers: list[str],
    rescued: RescuedFolios,
    similarity_threshold: float = 0.85,
) -> list[str]:
    """Strip the running footer, adding the folios it carried to ``rescued``.

    Same contract as ``remove_running_headers``, at the other edge.
    """
    cleaned_pages = []
    for index, page_text in enumerate(pages_text):
        lines = page_text.strip().split("\n")
        footer_indices: set[int] = set()
        lines_checked = 0
        for idx in range(len(lines) - 1, -1, -1):
            if lines_checked >= 3:
                break
            if not lines[idx].strip():
                continue
            lines_checked += 1
            normalized = _normalize_header_line(lines[idx])
            if normalized:
                for footer in running_footers:
                    if _strings_are_similar(normalized, footer, similarity_threshold):
                        footer_indices.add(idx)
                        break
        cleaned_lines: list[str] = []
        for idx, line in enumerate(lines):
            if idx in footer_indices:
                # The footer goes; the number it carried is handed on.
                rescued.add(index, "bottom", _extract_edge_page_number(line))
                continue
            cleaned_lines.append(line)
        cleaned_pages.append("\n".join(cleaned_lines))
    return cleaned_pages


def remove_running_footers_from_blocks(
    blocks: list[list[str] | None],
    running_footers: list[str],
    rescued: RescuedFolios,
    similarity_threshold: float = 0.85,
) -> list[list[str] | None]:
    """Take the running footer out of a cut footnote block.

    Where the page geometry cut an apparatus, the foot of the page went with
    it: the running footer is then the last line of the block, not of the
    body, and ``remove_running_footers`` never sees it. Left there it becomes
    footnote text -- on SSOAR 35056, 15 of 34 definitions ended in the
    publisher's name and three consisted of nothing else.

    A page number embedded in the removed line goes to ``rescued`` at the foot.
    That folio belongs to the body: it is the page's own number, and dropping it
    with the footer would leave the page unlabelled.
    """
    cleaned_blocks: list[list[str] | None] = []
    for index, block in enumerate(blocks):
        if not block or not running_footers:
            cleaned_blocks.append(block)
            continue
        kept, folio = [], None
        for line in block:
            normalized = _normalize_header_line(line)
            if normalized and any(
                _strings_are_similar(normalized, f, similarity_threshold)
                for f in running_footers
            ):
                # The first only. Where the head strippers hand on every number
                # they find, this one is reaching into an apparatus: a second
                # match inside a note block is another note's text, not another
                # folio, and the numbers there are note numbers.
                folio = folio or _extract_edge_page_number(line)
                continue
            kept.append(line)
        rescued.add(index, "bottom", folio)
        cleaned_blocks.append(kept)
    return cleaned_blocks


def strip_running_elements(
    pages_text: list[str],
    rescued: RescuedFolios | None = None,
    header_min: int = 3,
    footer_min: int | None = None,
    similarity_threshold: float = 0.85,
    foot_blocks: list[list[str] | None] | None = None,
    known: KnownTitles | None = None,
    heads: HeadCandidates | None = None,
    lists: frozenset[int] | set[int] = frozenset(),
    kept: list[tuple[int, str]] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Convenience: detect + remove headers and footers in one call.

    ``foot_blocks`` are footnote blocks the page geometry has already cut off.
    They are not cleaned here -- that is
    ``remove_running_footers_from_blocks`` -- but they take part in *detecting*
    the footers: a volume whose apparatus swallows the running footer on most
    of its pages would otherwise show it on too few to reach the threshold.

    ``rescued`` collects the folio each removed running element carried, for the
    consensus to weigh. A caller with no use for them may leave it out; the
    numbers are then dropped with the lines they stood in.

    ``known`` and ``heads`` pass to ``remove_running_headers``: with both, a
    head line bearing a title the volume names is deferred to the placement
    rather than deleted here. ``kept`` collects the head lines left standing
    as the titles of the pages they open.

    Returns (cleaned_pages, detected_headers, detected_footers).
    """
    if rescued is None:
        rescued = RescuedFolios(len(pages_text))
    headers = detect_running_headers(pages_text, header_min, similarity_threshold)
    cleaned = remove_running_headers(
        pages_text, headers, rescued, similarity_threshold, known, heads, lists,
        kept)
    whole_pages = cleaned
    if foot_blocks is not None:
        whole_pages = [
            text if not block else text + "\n" + "\n".join(block)
            for text, block in zip(cleaned, foot_blocks)
        ]
    footers = detect_running_footers(whole_pages, footer_min, similarity_threshold)
    cleaned = remove_running_footers(
        cleaned, footers, rescued, similarity_threshold)
    return cleaned, headers, footers
