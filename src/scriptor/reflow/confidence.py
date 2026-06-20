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
    is ordered best-first.
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
