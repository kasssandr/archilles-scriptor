"""Authoring aid for ground truth.

This module prepares material for a human: page images, raw text to copy
from, and an empty truth.toml skeleton. It deliberately contributes no
judgement of its own — no detected footnotes, no guessed anchors, nothing
from reflow. Truth is written against the printed page, so that the
benchmark cannot end up measuring how well Scriptor agrees with itself.

It is not part of the measuring path and may therefore use pymupdf, which
the metric modules must not.
"""
from __future__ import annotations

import hashlib
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from scriptor.eval.corpus import SourceMeta

_CHUNK = 1 << 20
_UA = "scriptor-eval/1.0 (benchmark corpus fetch)"


@dataclass(frozen=True)
class PageRef:
    """One physical page and the label its catalogue prints for it."""
    index: int      # 1-based file ordinal
    label: str      # printed label, always a string ("xiv", "14")


def choose_pages(
    refs: list[PageRef], body_range: tuple[int, int], count: int, seed: int
) -> list[str]:
    """Draw `count` page labels from the body range, reproducibly.

    The body range is the operator's documented decision about where running
    text begins and ends; guessing it would mean sorting registers and blank
    pages by heuristic, which is exactly the kind of judgement this module
    must not make. Returns labels in printed order.
    """
    first, last = body_range
    pool = [r for r in refs if first <= r.index <= last]
    if count > len(pool):
        raise ValueError(
            f"asked for {count} pages but the body range holds only {len(pool)}"
        )
    picked = random.Random(seed).sample(pool, count)
    picked.sort(key=lambda r: r.index)
    return [r.label for r in picked]


# fetching -----------------------------------------------------------------


class ChecksumError(RuntimeError):
    """The fetched file is not the one the corpus was built against."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, expected: str) -> None:
    actual = _sha256(Path(path))
    if actual != expected.lower():
        raise ChecksumError(
            f"{path}: expected sha256 {expected.lower()}, got {actual}"
        )


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(request) as response, open(dest, "wb") as out:
        while chunk := response.read(_CHUNK):
            out.write(chunk)


def fetch_pdf(meta: SourceMeta, dest: Path) -> Path:
    """Fetch the band's PDF unless a matching copy is already there.

    A mismatching download is deleted rather than kept: a corpus entry whose
    bytes differ from the recorded checksum would silently invalidate every
    page reference authored against it.
    """
    dest = Path(dest)
    if dest.exists():
        try:
            verify_checksum(dest, meta.sha256)
            return dest
        except ChecksumError:
            dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _download(meta.url, dest)
    try:
        verify_checksum(dest, meta.sha256)
    except ChecksumError:
        dest.unlink(missing_ok=True)
        raise
    return dest
