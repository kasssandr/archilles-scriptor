"""`pages-zip` source adapter — ZIP/dir of per-page TXT -> renumbered pages dir.

Internet-Archive and similar public-domain scans ship their OCR as a set of
per-page text files (often inside a ZIP). This adapter collects those files,
sorts them into natural page order, drops obvious non-page artifacts
(thumbnails, XML/JSON metadata, macOS junk), decodes them robustly (legacy
OCR text is not always UTF-8) and rewrites them as zero-padded
``00000001.txt …`` so the existing reflow stage can ingest them unchanged
(`scriptor.reflow.core.main` globs ``[0-9]*.txt`` in sorted order).

Empty/near-empty pages are *kept* (renumbered like any other) so page
continuity is preserved; the reflow's ``parse_page`` already skips truly
empty pages on its own.
"""

from __future__ import annotations

import re

# Archive members that are never a text page. Matched against the base name.
_SKIP_NAME_RE = re.compile(
    r"(__ia_thumb|_thumb|metadata|^_meta|scandata|marc|__MACOSX|\.DS_Store)",
    re.IGNORECASE,
)

_NUM_RE = re.compile(r"(\d+)")


def natural_sort_key(name: str) -> list:
    """Split a filename so digit runs sort numerically (`page_9` < `page_10`)."""
    return [int(p) if p.isdigit() else p.lower() for p in _NUM_RE.split(name)]


def is_page_file(name: str) -> bool:
    """True if an archive member looks like a per-page text file."""
    base = name.rsplit("/", 1)[-1]
    if not base.lower().endswith(".txt"):
        return False
    if _SKIP_NAME_RE.search(name):
        return False
    return True
