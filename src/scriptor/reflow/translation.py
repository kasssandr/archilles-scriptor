"""Translation profile (stage 2c): master Markdown -> translation-ready MD.

Pure string post-processor (no I/O). Protects elements that must not be
translated with <dnt>…</dnt> tags and removes open confidence flags
(strip-and-pass). See
docs/superpowers/specs/2026-06-21-uebersetzungs-profil-design.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable

DNT_OPEN = "<dnt>"
DNT_CLOSE = "</dnt>"

# http(s):// or www.… up to whitespace/'<'. Trailing punctuation is split off
# during wrapping (see protect_urls), not here.
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<]+", re.IGNORECASE)

# Title quote pairs: German „…“, straight "…", guillemets »…«.
QUOTE_PAIRS = [("„", "“"), ('"', '"'), ("»", "«")]

# Pandoc footnote definition line (single-line).
FN_DEF_RE = re.compile(r"^\[\^\d+\]:")

# A bibliography entry, as ``reflow/references.py`` leaves it: one entry, one
# paragraph, opening with its own number. Stricter than the rule over there,
# because here there is no reference block around the line to vouch for it — a
# name and a year have to stand in the text itself, or "[3] ist der Beleg für die
# vorstehende Behauptung" would be protected as a citation.
REFERENCE_ENTRY_RE = re.compile(
    r"^\[\d{1,3}\]\s+[A-ZÄÖÜ].*\b(?:1[5-9]\d\d|20\d\d|21\d\d)\b"
)

# Confidence flags from the 2-B layer: [?FN:…] / [??FN:…] (optional leading space).
FLAG_RE = re.compile(r" ?\[\?\??FN:[^\]]*\]")

# Existing <dnt>…</dnt> span (transformation applies only outside of it).
_DNT_SPAN_RE = re.compile(r"<dnt>.*?</dnt>", re.DOTALL)
_URL_TRAIL = ".,;:!?)]"


def strip_flags(text: str) -> str:
    """Removes open confidence flags (strip-and-pass, §9-Q2). Body stays
    unchanged; orphaned footnote definitions are preserved."""
    return FLAG_RE.sub("", text)


def strip_dnt(text: str) -> str:
    """Removes the DNT tags, keeps the inner text (round-trip inverse of
    wrapping). Archillator runs this after translation."""
    return text.replace(DNT_OPEN, "").replace(DNT_CLOSE, "")


def _transform_outside_dnt(text: str, transform: Callable[[str], str]) -> str:
    """Applies ``transform`` only to the text parts *outside* existing
    <dnt>…</dnt> spans; existing spans are left untouched. This keeps all
    protect_* functions idempotent and avoids nesting."""
    out: list[str] = []
    last = 0
    for m in _DNT_SPAN_RE.finditer(text):
        out.append(transform(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(transform(text[last:]))
    return "".join(out)


def protect_urls(text: str) -> str:
    """Tags URLs with <dnt>…</dnt>. Trailing punctuation stays outside the
    tag. Skips URLs already tagged."""
    def _wrap(m: re.Match) -> str:
        url = m.group(0)
        trail = ""
        while url and url[-1] in _URL_TRAIL:
            trail = url[-1] + trail
            url = url[:-1]
        return f"{DNT_OPEN}{url}{DNT_CLOSE}{trail}"

    return _transform_outside_dnt(text, lambda s: URL_RE.sub(_wrap, s))


def protect_quoted(text: str) -> str:
    """Tags quoted titles (all QUOTE_PAIRS) with <dnt>…</dnt>.
    Only outside existing tags; idempotent."""
    def _wrap(seg: str) -> str:
        for open_q, close_q in QUOTE_PAIRS:
            pattern = re.escape(open_q) + "[^" + re.escape(close_q) + "]*" + re.escape(close_q)
            seg = re.sub(
                pattern,
                lambda m: f"{DNT_OPEN}{m.group(0)}{DNT_CLOSE}",
                seg,
            )
        return seg

    return _transform_outside_dnt(text, _wrap)


def prepare_translation(markdown: str) -> str:
    """Master Markdown -> translation-ready MD: strip flags; tag URLs
    everywhere; on footnote-definition lines, additionally tag quoted
    titles. Idempotent; structural Pandoc markers are left untouched."""
    text = strip_flags(markdown)
    out_lines: list[str] = []
    for line in text.split("\n"):
        if REFERENCE_ENTRY_RE.match(line):
            # Whole-line protection, and no inner tagging afterwards: a citation
            # is one unit — author, title, venue, year — and every part of it is
            # a thing a translator must leave alone.
            out_lines.append(f"{DNT_OPEN}{line}{DNT_CLOSE}")
            continue
        line = protect_urls(line)
        if FN_DEF_RE.match(line):
            line = protect_quoted(line)
        out_lines.append(line)
    return "\n".join(out_lines)


BRIEFING = """Translation briefing
====================
This document has been prepared for LLM translation.

1. Translate the running prose into the target language.
2. Leave text inside <dnt>…</dnt> exactly as it stands. Never translate,
   reorder or normalise it. What is protected this way: referenced work and
   article titles, bibliographic references, URLs.
3. Leave untagged work titles, proper names and bibliographic references
   verbatim as well, especially inside the footnote apparatus. When in doubt,
   do not translate. Bibliographic precision outranks completeness.
4. Carry over Pandoc structures unchanged: footnote markers [^N], footnote
   definitions [^N]:, page markers [p. …]. A page label may be roman ([p. xiv]);
   it is the page as printed in the book and must never be renumbered.
5. After translating, remove the <dnt> and </dnt> tags and keep the text
   between them.
"""
