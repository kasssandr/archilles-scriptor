"""Confidence layer (Etappe 2-B): locate likely positions of lost footnote
markers and emit inline uncertainty flags into the annotated master.

Deterministic, page-local, additive — operates on reconstructed paragraphs
(local ``[n]`` markers) without touching ``reconstruct_body``. See
docs/superpowers/specs/2026-06-20-confidence-layer-design.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scriptor.reflow.footnotes import PLACED_MARKER_RE

# Confidence-class threshold for a single candidate (named, tunable).
T_DEFAULT = 0.5
# Context-snippet half-width (chars) recorded in the audit.
SNIPPET_RADIUS = 30

# OCR confusion table: a single footnote digit -> glyphs it is commonly
# misread as when set as a small superscript. Data, not logic — tune freely.
OCR_CONFUSION: dict[int, set[str]] = {
    1: {"l", "I", "i", "ı", "|", "!", "j", "/"},
    2: {"z", "Z", "?", "²"},
    3: {"B", "8", "³"},
    4: {"A", "ı", "'", "⁴"},
    5: {"S", "⁵"},
    6: {"b", "G", "&", "⁶"},
    7: {"T", "/", "⁷"},
    8: {"B", "&", "⁸"},
    9: {"g", "q", "⁹"},
}

# Sentence-ending / closing punctuation that may follow a real marker.
_PUNCT_AFTER = set('.,;:!?»“"’\')]')


@dataclass
class Candidate:
    char: str
    confidence: float
    reason: str
    span: tuple[int, int]   # (start, end) offsets in the paragraph text


@dataclass
class FootnoteAnnotation:
    fn_num: int
    page: int
    klasse: str             # "vorgeschlagen" | "geraten" | "orphan"
    candidates: list[Candidate] = field(default_factory=list)
    scope: str = "page"


def score_candidate(left: str, right: str) -> tuple[float, str]:
    """Score a glyph by its immediate neighbours. Returns (score, reason).

    ``left`` is the char before the glyph ("" at start), ``right`` the char
    after ("" at end). Glyph plausibility itself is handled by the caller
    (only glyphs in the confusion set reach here).
    """
    score = 0.4
    reasons = ["glyph-in-table"]
    if left and left.isalpha():
        score += 0.3
        reasons.append("glued-to-word")
    if right == "" or right.isspace() or right in _PUNCT_AFTER:
        score += 0.2
        reasons.append("before-punct/space")
    return round(min(score, 1.0), 2), "+".join(reasons)


def find_candidates(
    interval: str, base_offset: int, num: int, T: float = T_DEFAULT
) -> list[Candidate]:
    """Search ``interval`` for glyphs that could be the lost marker ``num``.

    ``base_offset`` maps interval positions back into the paragraph. Result
    is ordered best-first. ``T`` is accepted for signature uniformity but not
    used here — classification by threshold happens in ``classify``.
    """
    glyphs = OCR_CONFUSION.get(num, set())
    out: list[Candidate] = []
    for i, ch in enumerate(interval):
        if ch in glyphs:
            left = interval[i - 1] if i > 0 else ""
            right = interval[i + 1] if i + 1 < len(interval) else ""
            score, reason = score_candidate(left, right)
            out.append(
                Candidate(
                    char=ch,
                    confidence=score,
                    reason=reason,
                    span=(base_offset + i, base_offset + i + 1),
                )
            )
    out.sort(key=lambda c: c.confidence, reverse=True)
    return out


def classify(candidates: list[Candidate], T: float = T_DEFAULT) -> str:
    """Map a candidate list to a confidence class."""
    if not candidates:
        return "orphan"
    if len(candidates) == 1 and candidates[0].confidence >= T:
        return "vorgeschlagen"
    return "geraten"


# Page marker "[S. NN]" — to attribute a candidate to its page.
_PAGE_MARKER_RE = re.compile(r"\[S\. (\d+)\]")


def _present_markers(para: str) -> dict[int, int]:
    """Present footnote number -> its start offset in the paragraph."""
    return {int(m.group(1)): m.start() for m in PLACED_MARKER_RE.finditer(para)}


def _page_of(para: str, offset: int) -> int:
    """Page number from the nearest [S. NN] marker at or before ``offset``."""
    page = -1
    for m in _PAGE_MARKER_RE.finditer(para):
        if m.start() <= offset:
            page = int(m.group(1))
        else:
            break
    return page


def annotate_paragraph(
    para: str, fns: dict[int, str], T: float = T_DEFAULT
) -> tuple[str, list[FootnoteAnnotation]]:
    """Insert uncertainty flags for unclaimed footnotes in one paragraph.

    A footnote ``num`` in ``fns`` is *unclaimed* when ``[num]`` is absent from
    ``para``. For each, search the interval between the nearest present
    markers around ``num`` for confusion glyphs, classify, and insert flag(s).
    Returns the annotated paragraph and the annotations found.
    """
    present = _present_markers(para)
    annotations: list[FootnoteAnnotation] = []
    insertions: list[tuple[int, str]] = []  # (offset, flag) — applied right-to-left

    for num in sorted(fns):
        if num in present:
            continue  # claimed — not uncertain
        lowers = [pos for n, pos in present.items() if n < num]
        uppers = [pos for n, pos in present.items() if n > num]
        start = max(lowers) if lowers else 0
        end = min(uppers) if uppers else len(para)
        if end < start:
            start, end = 0, len(para)
        cands = find_candidates(para[start:end], start, num, T)
        klasse = classify(cands, T)
        page = _page_of(para, start)

        if klasse == "orphan":
            annotations.append(FootnoteAnnotation(num, page, "orphan", []))
            insertions.append((len(para), f" [?FN:{num}]"))
        elif klasse == "vorgeschlagen":
            c = cands[0]
            annotations.append(FootnoteAnnotation(num, page, "vorgeschlagen", [c]))
            insertions.append((c.span[1], f"[?FN:{num}|{c.char}]"))
        else:  # geraten — one flag per candidate, at its own position
            annotations.append(FootnoteAnnotation(num, page, "geraten", cands))
            for c in cands:
                insertions.append(
                    (c.span[1], f"[??FN:{num}|{c.char}:{c.confidence:.1f}]")
                )

    out = para
    for offset, flag in sorted(insertions, key=lambda x: x[0], reverse=True):
        out = out[:offset] + flag + out[offset:]
    return out, annotations


class Annotator:
    """Stateful wrapper that annotates paragraphs and accumulates annotations
    across a whole render run."""

    def __init__(self, T: float = T_DEFAULT) -> None:
        self.T = T
        self.annotations: list[FootnoteAnnotation] = []

    def annotate(self, para: str, fns: dict[int, str]) -> str:
        out, anns = annotate_paragraph(para, fns, self.T)
        self.annotations.extend(anns)
        return out
