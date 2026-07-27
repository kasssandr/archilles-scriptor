"""Offset-preserving text normalization.

normalize() maps text to a canonical form (casefold, single spaces, soft
hyphens dropped, line-break hyphenation joined). find_snippet() searches a
normalized needle inside a haystack but answers with offsets into the
ORIGINAL haystack, via a position map built during normalization. Metrics
must always report positions a human can find in the real file.
"""
from __future__ import annotations

import unicodedata

_SOFT_HYPHEN = "­"


def _normalized_with_map(text: str) -> tuple[str, list[int]]:
    """Returns (normalized text, map: normalized index -> original index)."""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    posmap: list[int] = []
    i, n = 0, len(text)
    pending_space = False
    while i < n:
        ch = text[i]
        if ch == _SOFT_HYPHEN:
            i += 1
            continue
        # line-break hyphenation: "-\n" between letters joins the word
        if (ch == "-" and i + 1 < n and text[i + 1] == "\n"
                and out and out[-1].isalpha()
                and i + 2 < n and text[i + 2].isalpha()):
            i += 2
            continue
        if ch.isspace():
            pending_space = True
            i += 1
            continue
        if pending_space and out:
            out.append(" ")
            posmap.append(i)          # space attributed to the following char
        pending_space = False
        for c in ch.casefold():       # casefold may expand (ß -> ss)
            out.append(c)
            posmap.append(i)
        i += 1
    return "".join(out), posmap


def normalize(text: str) -> str:
    return _normalized_with_map(text)[0]


def find_snippet(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate normalized needle in haystack; return original-offset span."""
    norm_hay, posmap = _normalized_with_map(haystack)
    norm_needle = normalize(needle)
    if not norm_needle:
        return None
    idx = norm_hay.find(norm_needle)
    if idx < 0:
        return None
    start = posmap[idx]
    last = idx + len(norm_needle) - 1
    end = posmap[last] + 1
    return (start, end)
