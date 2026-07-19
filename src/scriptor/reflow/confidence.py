"""Confidence layer (Etappe 2-B): locate likely positions of lost footnote
markers and emit inline uncertainty flags into the annotated master.

Deterministic, page-local, additive — operates on reconstructed paragraphs
(local ``[n]`` markers) without touching ``reconstruct_body``. See
docs/superpowers/specs/2026-06-20-confidence-layer-design.md.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from scriptor._text import plural
from scriptor.reflow.footnotes import PLACED_MARKER_RE
from scriptor.reflow.pagelabel import PAGE_MARKER_RE, decode_label

# Confidence-class threshold for a single candidate (named, tunable).
T_DEFAULT = 0.5
# Context-snippet half-width (chars) recorded in the audit.
SNIPPET_RADIUS = 30

# --- how much a glyph's identity is worth, before position is considered ------
#
# A book is scanned once, in one typeface, by one engine. Whatever it makes of a
# superscript 1, it makes of every superscript 1. So the glyphs seen in this
# document's own sequence gaps say more than the flat table below ever can.
#
# Without that evidence every glyph in the table is equally likely: BASE_PRIOR.
# With it, a glyph's prior moves between PRIOR_MIN and PRIOR_MAX according to its
# share of the observations for that digit. The band is deliberately narrow — the
# prior alone must never decide. A candidate has to sit at a marker position to
# exist at all, and evidence may only *reweight and rank* the candidates the
# structural rules already found. It can never widen a gap or invent a footnote.
BASE_PRIOR = 0.4
PRIOR_MIN = 0.2
PRIOR_MAX = 0.6
# Below this many observations for a digit, the document has not said anything.
MIN_OBSERVATIONS = 3
# How far the best candidate must lead before a multi-candidate gap counts as
# settled rather than guessed. Only applied where evidence backs the margin.
DOMINANCE_MARGIN = 0.15

# OCR confusion table: a single footnote digit -> glyphs it is commonly
# misread as when set as a small superscript. Data, not logic — tune freely.
OCR_CONFUSION: dict[int, set[str]] = {
    1: {"l", "I", "i", "ı", "j"},
    2: {"z", "Z", "²"},
    3: {"B", "8", "³"},
    4: {"A", "ı", "'", "⁴"},
    5: {"S", "⁵"},
    6: {"b", "G", "&", "⁶"},
    7: {"T", "⁷"},
    8: {"B", "&", "⁸"},
    9: {"g", "q", "⁹"},
}
# Bare sentence punctuation (! ? / |) was removed above: at a marker position
# every "!" became a FN-1 candidate, every "?" a FN-2 candidate, etc. — pure
# review-master noise. Letters/superscripts only.

# A footnote marker is followed by a break (whitespace / end / closing or
# sentence punctuation) and attaches on its left to a word end, a sentence end
# (period or closing quote), or an opening paren ("(1)"). _PUNCT_AFTER is what
# may FOLLOW a marker; _ATTACH_BEFORE the non-letter chars that may precede one.
_PUNCT_AFTER = set('.,;:!?»“"’\')]')
_ATTACH_BEFORE = set('.!?»“"’\')(')


def _is_marker_position(left: str, right: str) -> bool:
    """True if a glyph with these neighbours sits where a real footnote marker
    can — i.e. a break follows it. A glyph wedged between two letters (mid-word)
    is never a marker; this hard filter stops the layer from flagging every
    'i'/'l' inside ordinary words."""
    return right == "" or right.isspace() or right in _PUNCT_AFTER


# Structural markers in a reconstructed paragraph that must NOT yield
# candidates: page markers "[p. NN]" and footnote markers "[n]"/"[^n]".
_MARKER_SPAN_RE = re.compile(r"\[p\. [^\]]+\]|\[\^?\d{1,3}\]")


def _mask_markers(text: str) -> str:
    """Blank out structural markers (same length) so the candidate search never
    matches a glyph inside e.g. the 'i' of '[p. xiv]' or a footnote marker."""
    return _MARKER_SPAN_RE.sub(lambda m: " " * (m.end() - m.start()), text)


@dataclass
class GlyphEvidence:
    """How often each glyph turned up as a candidate for each digit.

    ``counts`` are this document's own, and they are a pure function of it: the
    same pages always yield the same evidence, hence the same scores, hence the
    same decision file. Nothing accumulates between runs behind your back.

    ``pseudo`` are carried in from an OCR profile — glyphs a human confirmed in
    other volumes (see ``reflow/profile.py``). They are an explicit input, so
    reproducibility survives: same pages, same profile, same output. They are also
    deliberately few, so a book's own typography always outweighs the corpus
    average once the book has said anything at all.
    """

    counts: Counter = field(default_factory=Counter)          # (digit, glyph) -> seen here
    pseudo: dict[tuple[int, str], float] = field(default_factory=dict)

    def count(self, digit: int, glyph: str) -> int:
        """What *this document* shows. The honest number to report to a reader."""
        return self.counts[(digit, glyph)]

    def _weight(self, digit: int, glyph: str) -> float:
        return self.counts[(digit, glyph)] + self.pseudo.get((digit, glyph), 0.0)

    def glyphs_for(self, digit: int) -> set[str]:
        """Every glyph anyone has associated with that digit."""
        return {g for (d, g) in self.counts if d == digit} | {
            g for (d, g) in self.pseudo if d == digit
        }

    def observations(self, digit: int) -> float:
        return sum(self._weight(digit, g) for g in self.glyphs_for(digit))

    def informed(self, digit: int) -> bool:
        """Has anyone — this document, or a profile — said enough to be believed?"""
        return self.observations(digit) >= MIN_OBSERVATIONS

    def share(self, digit: int, glyph: str) -> float:
        total = self.observations(digit)
        return self._weight(digit, glyph) / total if total else 0.0

    def from_profile(self, digit: int) -> bool:
        return any(d == digit for d, _g in self.pseudo)

    def prior(self, digit: int, glyph: str) -> tuple[float, str]:
        """Prior score of the glyph itself, with the reason it earned."""
        if not self.informed(digit):
            return BASE_PRIOR, "glyph-in-table"
        share = self.share(digit, glyph)
        score = PRIOR_MIN + (PRIOR_MAX - PRIOR_MIN) * share
        reason = f"glyph-share-{share:.0%}"
        if self.from_profile(digit):
            reason += "+profile"
        return round(score, 2), reason


NO_EVIDENCE = GlyphEvidence()


@dataclass
class Candidate:
    char: str
    confidence: float
    reason: str
    span: tuple[int, int]   # (start, end) offsets in the paragraph text
    context: str = ""       # surrounding text, so a human can find the spot
    seen: int = 0           # times this glyph stood for this digit in the document


@dataclass
class FootnoteAnnotation:
    fn_num: int
    page: str               # printed page label ("xiv", "312"); "" if unknown
    confidence_class: str   # "suggested" | "guessed" | "orphan"
    candidates: list[Candidate] = field(default_factory=list)
    scope: str = "page"


def score_candidate(
    left: str,
    right: str,
    prior: float = BASE_PRIOR,
    prior_reason: str = "glyph-in-table",
) -> tuple[float, str]:
    """Score a glyph by its prior and its immediate neighbours. (score, reason).

    ``left`` is the char before the glyph ("" at start), ``right`` the char
    after ("" at end). Glyph plausibility itself is handled by the caller
    (only glyphs in the confusion set reach here); ``prior`` is how much that
    glyph is worth for this digit, flat by default and empirical when the
    document has spoken (see ``GlyphEvidence``).
    """
    score = prior
    reasons = [prior_reason]
    if left.isalpha() or left in _ATTACH_BEFORE:
        score += 0.3
        reasons.append("attached")
    if right in _PUNCT_AFTER:
        score += 0.2
        reasons.append("before-close-punct")
    elif right == "" or right.isspace():
        score += 0.1
        reasons.append("before-space")
    return round(min(score, 1.0), 2), "+".join(reasons)


def find_candidates(
    interval: str,
    base_offset: int,
    num: int,
    T: float = T_DEFAULT,
    evidence: GlyphEvidence | None = None,
) -> list[Candidate]:
    """Search ``interval`` for glyphs that could be the lost marker ``num``.

    ``base_offset`` maps interval positions back into the paragraph. Result
    is ordered best-first. ``T`` is accepted for signature uniformity but not
    used here — classification by threshold happens in ``classify``.

    ``evidence`` reorders and reweights; it never changes *which* glyphs qualify.
    That set is fixed by the confusion table and by the marker-position rule.
    """
    ev = evidence or NO_EVIDENCE
    glyphs = OCR_CONFUSION.get(num, set())
    masked = _mask_markers(interval)
    out: list[Candidate] = []
    for i, ch in enumerate(masked):
        if ch not in glyphs:
            continue
        left = masked[i - 1] if i > 0 else ""
        right = masked[i + 1] if i + 1 < len(masked) else ""
        if not _is_marker_position(left, right):
            continue  # mid-word — never a real marker
        prior, prior_reason = ev.prior(num, ch)
        score, reason = score_candidate(left, right, prior, prior_reason)
        out.append(
            Candidate(
                char=ch,
                confidence=score,
                reason=reason,
                span=(base_offset + i, base_offset + i + 1),
                seen=ev.count(num, ch),
            )
        )
    # Best first; ties keep their position order, so the ranking is reproducible.
    out.sort(key=lambda c: c.confidence, reverse=True)
    return out


def classify(
    candidates: list[Candidate], T: float = T_DEFAULT, dominance: bool = False
) -> str:
    """Map a candidate list to a confidence class.

    ``dominance`` may only be set where the document's own glyph statistics back
    the score gap. Without them a lead means merely "better placed", which is not
    enough to call a choice settled; with them it means "this book writes the
    digit that way", which is.
    """
    if not candidates:
        return "orphan"
    best = candidates[0]
    if len(candidates) == 1:
        return "suggested" if best.confidence >= T else "guessed"
    if (
        dominance
        and best.confidence >= T
        and best.confidence - candidates[1].confidence >= DOMINANCE_MARGIN
    ):
        return "suggested"
    return "guessed"


def _present_markers(para: str) -> dict[int, int]:
    """Present footnote number -> its start offset in the paragraph."""
    return {int(m.group(1)): m.start() for m in PLACED_MARKER_RE.finditer(para)}


def _page_of(para: str, offset: int) -> str:
    """Printed page label of the nearest [p. …] marker at or before ``offset``.

    Returns the label, because that is what the reader looks up on the scan.
    """
    page = ""
    for m in PAGE_MARKER_RE.finditer(para):
        if m.start() <= offset:
            page = m.group(1)
        else:
            break
    return page


def _context(para: str, span: tuple[int, int]) -> str:
    start = max(0, span[0] - SNIPPET_RADIUS)
    end = min(len(para), span[1] + SNIPPET_RADIUS)
    return " ".join(para[start:end].split())


def analyse_paragraph(
    para: str,
    fns: dict[int, str],
    T: float = T_DEFAULT,
    evidence: GlyphEvidence | None = None,
) -> list[FootnoteAnnotation]:
    """Find the unclaimed footnotes of one paragraph and their candidate glyphs.

    A footnote ``num`` in ``fns`` is *unclaimed* when ``[num]`` is absent from
    ``para``. Only unclaimed footnotes that form an *interior gap* — bounded by
    a present marker both below and above (number order) — are considered; the
    interval between those two markers is searched for confusion glyphs and
    classified.

    Pure analysis, no text change. Three callers share it: the review renderer
    (inserts flags), the decisions template (lists candidates for a human) and
    the decision applier (places the accepted marker). One place decides what a
    candidate is.
    """
    ev = evidence or NO_EVIDENCE
    present = _present_markers(para)
    annotations: list[FootnoteAnnotation] = []

    for num in sorted(fns):
        if num in present:
            continue  # claimed — not uncertain
        # Only flag a missing marker that is a genuine *interior gap* in the
        # recognised sequence — bounded by a confidently placed marker both
        # below and above it (number order). Edge gaps and paragraphs without a
        # coherent sequence are left unflagged; the hanging-reference rescue
        # still preserves the footnote text. Keeps flagging conservative: only
        # where the logic is sure a marker is missing between two known ones.
        lower_n = max((n for n in present if n < num), default=None)
        upper_n = min((n for n in present if n > num), default=None)
        if lower_n is None or upper_n is None:
            continue
        start, end = present[lower_n], present[upper_n]
        if end < start:
            continue
        cands = find_candidates(para[start:end], start, num, T, ev)
        for c in cands:
            c.context = _context(para, c.span)
        cls = classify(cands, T, dominance=ev.informed(num))
        annotations.append(FootnoteAnnotation(num, _page_of(para, start), cls, cands))
    return annotations


def collect_evidence(
    paragraphs: list[str],
    footnotes: list[dict[int, str]],
    T: float = T_DEFAULT,
    pseudo: dict[tuple[int, str], float] | None = None,
) -> GlyphEvidence:
    """Pass one: count, over the whole document, which glyphs stand in the gaps.

    No glyph can confirm itself into dominance here. What is counted is the set of
    candidates, and that set is settled by the confusion table and the
    marker-position rule — evidence may only reweight and rank it. Scoring with the
    flat prior makes that independence plain rather than merely true.
    """
    counts: Counter = Counter()
    for para, fns in zip(paragraphs, footnotes):
        for a in analyse_paragraph(para, fns, T):
            for c in a.candidates:
                counts[(a.fn_num, c.char)] += 1
    return GlyphEvidence(counts, dict(pseudo or {}))


def annotate_paragraph(
    para: str,
    fns: dict[int, str],
    T: float = T_DEFAULT,
    evidence: GlyphEvidence | None = None,
) -> tuple[str, list[FootnoteAnnotation]]:
    """Insert uncertainty flags for the unclaimed footnotes of one paragraph.
    Returns the annotated paragraph and the annotations behind it."""
    annotations = analyse_paragraph(para, fns, T, evidence)
    insertions: list[tuple[int, str]] = []  # (offset, flag), applied right-to-left
    present = _present_markers(para)

    for a in annotations:
        if a.confidence_class == "orphan":
            # Upper bound of the gap (PREPARED_FORMAT_SPEC §4.3): the flag
            # stands before the next placed marker, after every sentence the
            # lost one could have belonged to. Orphans are always interior
            # gaps, so the upper marker exists; len(para) is belt and braces.
            upper = min((n for n in present if n > a.fn_num), default=None)
            if upper is None:
                insertions.append((len(para), f" [?FN:{a.fn_num}]"))
            else:
                insertions.append((present[upper], f"[?FN:{a.fn_num}]"))
        elif a.confidence_class == "suggested":
            c = a.candidates[0]
            insertions.append((c.span[1], f"[?FN:{a.fn_num}|{c.char}]"))
        else:  # guessed: one flag per candidate, at its own position
            for c in a.candidates:
                insertions.append(
                    (c.span[1], f"[??FN:{a.fn_num}|{c.char}:{c.confidence:.1f}]")
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

    def annotate(
        self, para: str, fns: dict[int, str], evidence: GlyphEvidence | None = None
    ) -> str:
        out, anns = annotate_paragraph(para, fns, self.T, evidence)
        self.annotations.extend(anns)
        return out


def render_audit(
    annotations: list[FootnoteAnnotation],
    total_fn_defs: int,
    page_count: int,
    out_path: str,
) -> str:
    """Build the extended audit sidecar text: a run summary plus one block per
    uncertain footnote with its candidates and reasons."""
    uncertain = len(annotations)
    secure = max(total_fn_defs - uncertain, 0)
    multi = sum(1 for a in annotations if len(a.candidates) > 1)
    lines = [
        f"# Footnote confidence audit for {out_path}",
        f"# {plural(page_count, 'page')}, {plural(secure, 'certain footnote')}, "
        f"{uncertain} uncertain, {multi} with several candidates.",
        "# Convention: flag numbers are page-local (as printed on the scan); [^N]",
        "# are document-wide. Only sequence gaps between recognised markers are",
        "# flagged; a single letter at a word end (l/i for footnote 1) may be a",
        "# false positive.",
        "",
    ]
    # Sort by the label's ordinal, not the label itself: sorting "10" before "9"
    # as strings would scramble the audit exactly where it is longest.
    def _order(a: FootnoteAnnotation) -> tuple[int, int]:
        n = decode_label(a.page)
        return (-1 if n is None else n, a.fn_num)

    for a in sorted(annotations, key=_order):
        if a.candidates:
            cand = ", ".join(f"{c.char}:{c.confidence:.1f} ({c.reason})" for c in a.candidates)
        else:
            cand = "no candidate; kept as a hanging reference at the end of the paragraph"
        lines.append(f"p. {a.page}: FN {a.fn_num} [{a.confidence_class}]  ->  {cand}")
    return "\n".join(lines) + "\n"
