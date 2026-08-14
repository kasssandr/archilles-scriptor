"""Invisible characters: what they mean, and what to do about each kind.

A PDF hands over characters the reader never sees. Some carry information the
pipeline needs, some carry none, and some are a broken encoding wearing the
costume of a character. Treating them alike loses text either way -- keeping
them splits words for anyone searching the master, dropping them all throws
away the one mark that says where a word was broken.

Three kinds, three answers:

``U+00AD`` soft hyphen
    Where a word was broken across lines. Better evidence than a plain "-",
    which may be a compound hyphen; a soft hyphen never is. Turned into "-" at
    a line end so the existing de-hyphenation takes it from there, and dropped
    anywhere else, where it marks a break the renderer did not use.

zero-width marks
    Break opportunities left for the renderer. They mean nothing and go.

control characters and private-use codes
    A font that lost its ``ToUnicode`` mapping. What each one stands for is not
    guessed but read off the document's own spelling: where "first" also occurs
    unbroken, "\\x7frst" proves that U+007F is "fi". Counted per character over
    the whole document; a character nothing vouches for is dropped and
    reported, never invented.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

SOFT_HYPHEN = "­"

# Break opportunities and byte-order marks. No text, no structure, no trace.
ZERO_WIDTH = "​‌‍﻿"

# The ligatures a latin typeface sets as one glyph. Only these are offered as
# readings for a broken character: this is a repair of a known typographic
# mechanism, not a general-purpose spelling corrector.
LIGATURES = ("fi", "fl", "ff", "ffi", "ffl", "ft", "st")

# How much spelling evidence establishes a reading. Two independent words are
# not much, but the alternative readings are so few that a coincidence twice
# over is already unlikely -- and the measured cases are far above it: over the
# Oxford Handbook, U+007F draws 27 confirmations for "fi" against 1 for "st",
# U+0080 draws 9 for "fl" against 1. A character with one confirmation (U+0015,
# 3 word forms) stays unresolved and is dropped, which is the right answer:
# nothing in that document says what it was.
MIN_GLYPH_EVIDENCE = 2

# ... and by how much the winner has to lead. Below this the reading is a
# coin toss and the character is dropped instead.
GLYPH_MARGIN = 2.0

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def _is_broken(ch: str) -> bool:
    """A character that stands for something the file failed to state."""
    if ch in ZERO_WIDTH or ch == SOFT_HYPHEN or ch in "\n\t\r":
        return False
    return unicodedata.category(ch) in ("Cc", "Cf", "Co")


@dataclass
class CharacterReport:
    resolved: dict[str, str] = field(default_factory=dict)   # char -> ligature
    dropped: Counter = field(default_factory=Counter)        # char -> count
    soft_hyphens: int = 0        # turned into line-break hyphens
    zero_width: int = 0          # removed


def learn_broken_glyphs(pages: list[list[str]]) -> dict[str, str]:
    """Which ligature each broken character stands for, per document.

    Evidence is the document's own spelling: a broken word form whose repair
    yields a word the document also writes out. Counted per character rather
    than per word, because a file that breaks a ligature breaks it everywhere --
    "figures" never appears intact in the Oxford Handbook, while "first" does.
    Asking each word for its own proof would resolve 37 of 225 forms; asking the
    character resolves all of them from those 37.
    """
    intact: Counter[str] = Counter()
    broken: set[str] = set()
    for lines in pages:
        for line in lines:
            for word in _WORD.findall(line):
                intact[word.lower()] += 1
            # A damaged word form is letters and damaged characters and nothing
            # else. Admitting a token with digits or punctuation in it lets the
            # repair prove itself: at Asclepios "8\x08" read as "st" yielded
            # "8st", a word pattern that skips digits reported the word "st",
            # and "st" does occur in that volume -- so forty numbered lines
            # established a reading that was never there.
            for word in re.findall(r"\S+", line):
                if any(_is_broken(c) for c in word) and all(
                    _is_broken(c) or (c.isalpha() and not c.isdigit())
                    for c in word
                ):
                    broken.add(word.lower())

    votes: dict[str, Counter] = {}
    for word in broken:
        for ch in {c for c in word if _is_broken(c)}:
            tally = votes.setdefault(ch, Counter())
            for lig in LIGATURES:
                repaired = word.replace(ch, lig)
                candidate = _WORD.findall(repaired)
                # The repair has to yield exactly one word, that word has to be
                # the whole of what it repaired, it has to say more than the
                # ligature it inserted, and the document has to write it out.
                if (len(candidate) == 1
                        and candidate[0] == repaired
                        and len(candidate[0]) > len(lig)
                        and intact.get(candidate[0], 0) > 0):
                    tally[lig] += 1

    out: dict[str, str] = {}
    for ch, tally in votes.items():
        if not tally:
            continue
        (best, top), *rest = tally.most_common()
        runner_up = rest[0][1] if rest else 0
        if top >= MIN_GLYPH_EVIDENCE and top >= GLYPH_MARGIN * max(runner_up, 1):
            out[ch] = best
    return out


def resolve_characters(
    pages: list[list[str]],
    glyphs: dict[str, str] | None = None,
) -> tuple[list[list[str]], CharacterReport]:
    """Rewrite every page's lines so nothing invisible survives.

    Takes the document one line at a time and keeps the line structure, because
    a soft hyphen only means "this word was broken" at the end of one, and
    because the callers hold indent and type-size lists parallel to these lines.

    ``glyphs`` lets a caller supply a reading learnt elsewhere -- the body and
    the apparatus of one volume are set in the same font and have to be read
    the same way, but the apparatus alone is too little text to learn from.
    """
    report = CharacterReport(
        resolved=learn_broken_glyphs(pages) if glyphs is None else dict(glyphs)
    )
    out: list[list[str]] = []
    for lines in pages:
        new_lines: list[str] = []
        for line in lines:
            # The soft hyphen first: at a line end it becomes the hyphen the
            # de-hyphenation knows, elsewhere it is an unused break and goes.
            stripped = line.rstrip()
            if stripped.endswith(SOFT_HYPHEN):
                report.soft_hyphens += 1
                line = stripped[: -len(SOFT_HYPHEN)] + "-" + line[len(stripped):]
            if SOFT_HYPHEN in line:
                line = line.replace(SOFT_HYPHEN, "")
            for ch in ZERO_WIDTH:
                if ch in line:
                    report.zero_width += line.count(ch)
                    line = line.replace(ch, "")
            for ch in {c for c in line if _is_broken(c)}:
                reading = report.resolved.get(ch)
                if reading is None:
                    report.dropped[ch] += line.count(ch)
                    line = line.replace(ch, "")
                else:
                    line = line.replace(ch, reading)
            new_lines.append(line)
        out.append(new_lines)
    return out, report


def describe(report: CharacterReport) -> str | None:
    """One line for stderr, or None where there was nothing to do."""
    parts: list[str] = []
    if report.soft_hyphens:
        parts.append(f"{report.soft_hyphens} soft hyphens read as line breaks")
    if report.zero_width:
        parts.append(f"{report.zero_width} zero-width marks removed")
    if report.resolved:
        shown = ", ".join(f"U+{ord(c):04X}->{lig}"
                          for c, lig in sorted(report.resolved.items()))
        parts.append(f"broken glyphs resolved from the document's spelling ({shown})")
    if report.dropped:
        shown = ", ".join(f"U+{ord(c):04X}x{n}"
                          for c, n in sorted(report.dropped.items()))
        parts.append(f"unreadable characters dropped ({shown})")
    return "; ".join(parts) if parts else None
