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
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from scriptor.eval.corpus import Selection, SourceMeta
from scriptor.eval.ground_truth import GroundTruth

MIN_DEFINITION_CHARS = 15

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


# page material and skeleton ----------------------------------------------


def read_page_refs(pdf: Path) -> tuple[list[PageRef], str]:
    """Every page with the label its catalogue prints, plus where labels came from.

    A document without PageLabels gets physical numbers as labels, and says so
    — silently substituting them would make an authored page reference
    ambiguous later.
    """
    refs: list[PageRef] = []
    catalogue_labels = 0
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            label = (page.get_label() or "").strip()
            if label:
                catalogue_labels += 1
            refs.append(PageRef(index=i, label=label or str(i)))
    return refs, ("catalogue" if catalogue_labels else "physical")


def write_page_material(
    pdf: Path, labels: list[str], out_dir: Path, dpi: int = 150
) -> list[Path]:
    """Write <label>.png and <label>.txt for each selected page.

    The image is what the operator reads; the text is only there to copy
    definition strings from, so that authoring is transcription rather than
    typing. Neither carries any structural interpretation.
    """
    refs, _ = read_page_refs(pdf)
    by_label = {r.label: r.index for r in refs}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with pymupdf.open(pdf) as doc:
        for label in labels:
            if label not in by_label:
                raise ValueError(f"page label {label!r} is not in this document")
            page = doc[by_label[label] - 1]
            png = out_dir / f"{label}.png"
            page.get_pixmap(dpi=dpi).save(png)
            txt = out_dir / f"{label}.txt"
            txt.write_text(page.get_text(), encoding="utf-8")
            written.extend([png, txt])
    return written


_SKELETON_HEAD = '''\
# Ground truth for {band_id} -- {bibliography}
# Licence: {license} ({license_class})
#
# Author this against pages/<label>.png, NOT against any converter output.
# pages/<label>.txt holds the raw textlayer; copy definition text from there.
#
# Per footnote, printed on the page:
#   page               the printed label, as a string
#   num                the printed, page-local number
#   definition_starts  first ~15-40 characters of the note text
#   status             intact | marker_lost | damaged
#   anchor_after       text right before the marker in the body (optional,
#                      omit when the marker is destroyed and you cannot tell)

volume = "{band_id}"
pages = [{pages}]

# Copy this block per footnote and remove the leading '# ':
# [[footnotes]]
# page = "{first_page}"
# num = 1
# definition_starts = ""
# status = "intact"
# anchor_after = ""
'''


def render_skeleton(meta: SourceMeta, selection: Selection) -> str:
    """A truth.toml the operator fills in; it asserts nothing by itself."""
    pages = selection.all_pages
    body = _SKELETON_HEAD.format(
        band_id=meta.band_id, bibliography=meta.bibliography,
        license=meta.license, license_class=meta.license_class,
        pages=", ".join(f'"{p}"' for p in pages),
        first_page=pages[0] if pages else "1",
    )
    if selection.targeted:
        notes = ["", "# Pages chosen on purpose, and what to look for:"]
        notes += [f"#   {t.page}: {t.reason}" for t in selection.targeted]
        body += "\n".join(notes) + "\n"
    return body


# acceptance ---------------------------------------------------------------


@dataclass
class CheckResult:
    ok: bool
    problems: list[str]


def check_truth(truth: GroundTruth, selection: Selection, raw_toml: str) -> CheckResult:
    """Accept a band only when its truth covers exactly the documented selection.

    A page drawn at random that carries no footnote is a legitimate and
    valuable case, but it has to be declared as empty: otherwise a forgotten
    page and a genuinely empty one look the same.
    """
    problems: list[str] = []
    want = selection.all_pages
    have = list(truth.pages)

    for page in want:
        if page not in have:
            problems.append(f"selected page {page!r} is missing from truth.pages")
    for page in have:
        if page not in want:
            problems.append(f"page {page!r} is in truth.pages but was never selected")

    empty = {str(p) for p in tomllib.loads(raw_toml).get("empty_pages", [])}
    with_notes = {f.page for f in truth.footnotes}
    for page in want:
        if page not in with_notes and page not in empty:
            problems.append(
                f"page {page!r} has no footnote and is not listed in empty_pages"
            )

    for f in truth.footnotes:
        if len(f.definition_starts.strip()) < MIN_DEFINITION_CHARS:
            problems.append(
                f"p. {f.page} note {f.num}: definition_starts is shorter than "
                f"{MIN_DEFINITION_CHARS} characters"
            )

    seen: set[tuple[str, int]] = set()
    for f in truth.footnotes:
        key = (f.page, f.num)
        if key in seen:
            problems.append(f"p. {f.page} note {f.num} is listed twice")
        seen.add(key)

    return CheckResult(ok=not problems, problems=problems)
