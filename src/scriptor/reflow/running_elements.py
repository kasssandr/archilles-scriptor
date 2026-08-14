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
# ("146 WILHELM HEIL" / "WILHELM HEIL 147") must survive so downstream
# page-number detection (parse_page) still sees it. We keep only the bare number
# in place of the removed running element — never invent one. This mirrors the
# leading/trailing-digit handling in _normalize_header_line: the module already
# treats an edge digit-run in a running element as a page number.
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


def detect_running_headers(
    pages_text: list[str],
    min_occurrences: int = 3,
    similarity_threshold: float = 0.85,
) -> list[str]:
    if len(pages_text) < min_occurrences:
        return []

    first_lines: list[str] = []
    for page_text in pages_text:
        lines_checked = 0
        for line in page_text.strip().split("\n"):
            if lines_checked >= 3:
                break
            if not line.strip():
                continue
            lines_checked += 1
            normalized = _normalize_header_line(line)
            if normalized and len(normalized) > 5:
                first_lines.append(normalized)

    groups: list[list] = []  # [canonical, count]
    for normalized in first_lines:
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


def remove_running_headers(
    pages_text: list[str],
    running_headers: list[str],
    similarity_threshold: float = 0.85,
) -> list[str]:
    cleaned_pages = []
    for page_text in pages_text:
        lines = page_text.strip().split("\n")
        cleaned_lines: list[str] = []
        lines_checked = 0
        for line in lines:
            if not line.strip():
                cleaned_lines.append(line)
                continue
            normalized = _normalize_header_line(line)
            is_header = False
            if lines_checked < 3 and normalized:
                lines_checked += 1
                for header in running_headers:
                    if _strings_are_similar(normalized, header, similarity_threshold):
                        is_header = True
                        break
            if not is_header:
                cleaned_lines.append(line)
            else:
                # Remove the title, but preserve an embedded page number.
                page_num = _extract_edge_page_number(line)
                if page_num is not None:
                    cleaned_lines.append(page_num)
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
    similarity_threshold: float = 0.85,
) -> list[str]:
    cleaned_pages = []
    for page_text in pages_text:
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
                # Remove the running footer, but preserve an embedded page number.
                page_num = _extract_edge_page_number(line)
                if page_num is not None:
                    cleaned_lines.append(page_num)
                continue
            cleaned_lines.append(line)
        cleaned_pages.append("\n".join(cleaned_lines))
    return cleaned_pages


def remove_running_footers_from_blocks(
    blocks: list[list[str] | None],
    running_footers: list[str],
    similarity_threshold: float = 0.85,
) -> tuple[list[list[str] | None], list[str | None]]:
    """Take the running footer out of a cut footnote block.

    Where the page geometry cut an apparatus, the foot of the page went with
    it: the running footer is then the last line of the block, not of the
    body, and ``remove_running_footers`` never sees it. Left there it becomes
    footnote text -- on SSOAR 35056, 15 of 34 definitions ended in the
    publisher's name and three consisted of nothing else.

    Returns the cleaned blocks and, per page, a page number that was embedded
    in the removed line. That folio belongs to the body: it is the page's own
    number, and dropping it with the footer would leave the page unlabelled.
    """
    cleaned_blocks: list[list[str] | None] = []
    rescued: list[str | None] = []
    for block in blocks:
        if not block or not running_footers:
            cleaned_blocks.append(block)
            rescued.append(None)
            continue
        kept, folio = [], None
        for line in block:
            normalized = _normalize_header_line(line)
            if normalized and any(
                _strings_are_similar(normalized, f, similarity_threshold)
                for f in running_footers
            ):
                folio = folio or _extract_edge_page_number(line)
                continue
            kept.append(line)
        cleaned_blocks.append(kept)
        rescued.append(folio)
    return cleaned_blocks, rescued


def strip_running_elements(
    pages_text: list[str],
    header_min: int = 3,
    footer_min: int | None = None,
    similarity_threshold: float = 0.85,
    foot_blocks: list[list[str] | None] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Convenience: detect + remove headers and footers in one call.

    ``foot_blocks`` are footnote blocks the page geometry has already cut off.
    They are not cleaned here -- that is
    ``remove_running_footers_from_blocks`` -- but they take part in *detecting*
    the footers: a volume whose apparatus swallows the running footer on most
    of its pages would otherwise show it on too few to reach the threshold.

    Returns (cleaned_pages, detected_headers, detected_footers).
    """
    headers = detect_running_headers(pages_text, header_min, similarity_threshold)
    cleaned = remove_running_headers(pages_text, headers, similarity_threshold)
    whole_pages = cleaned
    if foot_blocks is not None:
        whole_pages = [
            text if not block else text + "\n" + "\n".join(block)
            for text, block in zip(cleaned, foot_blocks)
        ]
    footers = detect_running_footers(whole_pages, footer_min, similarity_threshold)
    cleaned = remove_running_footers(cleaned, footers, similarity_threshold)
    return cleaned, headers, footers
