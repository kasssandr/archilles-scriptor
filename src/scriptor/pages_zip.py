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
import zipfile
from pathlib import Path

from charset_normalizer import from_bytes

# Directory-level junk — checked against the full archive member path.
_SKIP_PATH_RE = re.compile(r"__MACOSX|\.DS_Store", re.IGNORECASE)
# Filename-level junk — matched against the base name only.
_SKIP_NAME_RE = re.compile(
    r"(__ia_thumb|_thumb|metadata|^_meta|scandata|marc)",
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
    if _SKIP_PATH_RE.search(name):
        return False
    if _SKIP_NAME_RE.search(base):
        return False
    return True


def decode_bytes(data: bytes) -> tuple[str, bool]:
    """Decode page bytes. Returns (text, used_fallback).

    UTF-8 first (the common case, fast path); on failure fall back to
    charset_normalizer's best guess, and finally latin-1 (which never
    raises). ``used_fallback`` is True whenever the bytes were not valid
    UTF-8, so the caller can report how many pages needed guessing.
    """
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        best = from_bytes(data).best()
        if best is not None:
            return str(best), True
        return data.decode("latin-1"), True


def _iter_members(src: Path) -> list[tuple[str, bytes]]:
    """Yield (member_name, raw_bytes) for every regular file in a zip or dir."""
    if src.is_dir():
        out: list[tuple[str, bytes]] = []
        for p in sorted(src.rglob("*")):
            if p.is_file():
                out.append((p.relative_to(src).as_posix(), p.read_bytes()))
        return out
    with zipfile.ZipFile(src) as zf:
        out = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            out.append((info.filename, zf.read(info)))
        return out


def collect_page_texts(src: Path) -> tuple[list[tuple[str, str]], list[str], int]:
    """Collect ordered (name, text) page pairs from a zip or directory.

    Returns (pages, skipped_names, encoding_fallbacks) where ``pages`` is
    sorted into natural page order and filtered to text pages only.
    """
    members = _iter_members(Path(src))
    kept_raw: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    for name, data in members:
        if is_page_file(name):
            kept_raw.append((name, data))
        else:
            skipped.append(name)
    kept_raw.sort(key=lambda nb: natural_sort_key(nb[0]))
    pages: list[tuple[str, str]] = []
    fallbacks = 0
    for name, data in kept_raw:
        text, used_fallback = decode_bytes(data)
        fallbacks += int(used_fallback)
        pages.append((name, text))
    return pages, skipped, fallbacks
