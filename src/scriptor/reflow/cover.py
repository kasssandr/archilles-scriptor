"""A distributor's cover sheet in front of an article.

JSTOR and Persée put a page of their own in front of the article they
deliver: title, source, stable URL, terms of use. It is not the article's
text, and the reader has its metadata elsewhere. Read as running text it
opened the master as one paragraph and ran into the article's title.

The sheet is told by its boilerplate, not by its layout. These sentences
are the distributor's, word for word on every sheet, and an article does
not print them. Two of them are required, because a single one may stand
in an article's footnote ("Stable URL" in a reference). Only the first
page is asked: the sheet stands in front of the article or not at all.

What happens to the page is the regions' business: it becomes front matter,
which keeps its text in the master — the bundle's coverage check reads the
PDF page by page, and a page that disappeared would count as lost — and
takes it out of the default search.
"""

from __future__ import annotations

import re

_SIGNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "JSTOR": tuple(re.compile(p, re.I) for p in (
        r"Your use of the JSTOR archive indicates your acceptance",
        r"JSTOR is a not-for-profit service",
        r"is collaborating with JSTOR to digitize",
        r"Stable URL:\s*https?://(www\.)?jstor\.org/stable",
        r"Early Journal Content on JSTOR",
        r"made freely available to everyone in the world by JSTOR",
    )),
    "Persée": tuple(re.compile(p, re.I) for p in (
        r"Citer ce document\s*/\s*Cite this document",
        r"Fichier pdf généré le",
        r"https?://(www\.)?persee\.fr/doc/",
        r"Document généré le",
    )),
}

_REQUIRED = 2


def _flat(lines: list[str]) -> str:
    """The page as one string: a sign may break across lines, and a break
    behind a hyphen (``not-for-`` / ``profit``) is no word space."""
    text = " ".join(line.strip() for line in lines)
    return re.sub(r"-\s+", "-", re.sub(r"\s+", " ", text))


def distributor_cover(lines: list[str]) -> str | None:
    """The distributor whose cover sheet these lines are, or None."""
    text = _flat(lines)
    for name, signs in _SIGNS.items():
        if sum(1 for sign in signs if sign.search(text)) >= _REQUIRED:
            return name
    return None
