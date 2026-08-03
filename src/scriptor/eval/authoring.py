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
    """One physical page and whatever the file's catalogue claims about it.

    The catalogue label is a claim, not the truth: it is frequently absent,
    sometimes partial, and sometimes disagrees with the number printed on the
    page. It is carried here so the skeleton can offer it as a hint, never so
    that it can be used as an answer.
    """
    index: int                      # 1-based file ordinal
    catalogue_label: str | None     # what PageLabels says, if anything


def choose_pages(
    refs: list[PageRef], body_range: tuple[int, int], count: int, seed: int
) -> list[int]:
    """Draw `count` physical pages from the body range, reproducibly.

    The body range is the operator's documented decision about where running
    text begins and ends; guessing it would mean sorting registers and blank
    pages by heuristic, which is exactly the kind of judgement this module
    must not make. Returns physical page numbers in ascending order.
    """
    first, last = body_range
    pool = [r.index for r in refs if first <= r.index <= last]
    if count > len(pool):
        raise ValueError(
            f"asked for {count} pages but the body range holds only {len(pool)}"
        )
    return sorted(random.Random(seed).sample(pool, count))


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


def read_page_refs(pdf: Path) -> list[PageRef]:
    """Every physical page, with the catalogue's claim about it where it has one.

    A page without a PageLabels entry reports None rather than a substitute.
    Filling the gap with the physical number would invent a label that is
    neither in the catalogue nor on the page — exactly the confusion this
    module exists to avoid.
    """
    refs: list[PageRef] = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            label = (page.get_label() or "").strip()
            refs.append(PageRef(index=i, catalogue_label=label or None))
    return refs


def page_stem(physical: int) -> str:
    """File stem for one physical page: zero-padded so listings sort right."""
    return f"p{physical:03d}"


def write_page_material(
    pdf: Path, pages: list[int], out_dir: Path, dpi: int = 150
) -> list[Path]:
    """Write pNNN.png and pNNN.txt for each selected physical page.

    The image is what the operator reads; the text is only there to copy
    definition strings from, so that authoring is transcription rather than
    typing. Neither carries any structural interpretation, and neither is
    named after a label that has yet to be read off the page.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with pymupdf.open(pdf) as doc:
        for physical in pages:
            if not 1 <= physical <= len(doc):
                raise ValueError(
                    f"physical page {physical} is not in this document "
                    f"(it has {len(doc)})"
                )
            page = doc[physical - 1]
            stem = page_stem(physical)
            png = out_dir / f"{stem}.png"
            page.get_pixmap(dpi=dpi).save(png)
            txt = out_dir / f"{stem}.txt"
            txt.write_text(page.get_text(), encoding="utf-8")
            written.extend([png, txt])
    return written


_SKELETON_HEAD = '''\
# Ground truth for {band_id} -- {bibliography}
# Licence: {license} ({license_class})
#
# Author this against pages/pNNN.png, NOT against any converter output.
# pages/pNNN.txt holds the raw textlayer; copy definition text from there to
# save typing -- but read it back against the image. Extraction drops spaces,
# notably between words in Greek and other non-Latin passages, and a truth
# that copies such a defect measures the defect instead of the page.
#
# Two kinds of page number are in play, and they are not interchangeable:
#   pNNN            the physical page in the PDF -- the file name
#   printed label   the number or numeral printed on that page -- the truth
# They frequently disagree. Read the label off the image; where a catalogue
# entry exists it is offered below as a hint, and it may well be wrong.
#
# Fill in `pages` with the printed labels in reading order, and map each one
# to its physical page under [physical_pages].
#
# Per footnote, printed on the page:
#   page               the printed label, as a string
#   num                the number as printed -- page-local in some volumes,
#                      running through the whole book in others; copy what
#                      stands there, do not renumber
#   definition_starts  first ~15-40 characters of the note text
#   status             intact | marker_lost | damaged
#   anchor_after       text right before the marker in the body (optional,
#                      omit when the marker is destroyed and you cannot tell)
# A selected page carrying no footnote at all goes into `empty_pages`.

volume = "{band_id}"
pages = []
empty_pages = []

[physical_pages]
{physical_hints}
# Copy this block per footnote and remove the leading '# ':
# [[footnotes]]
# page = ""
# num = 1
# definition_starts = ""
# status = "intact"
# anchor_after = ""
'''


def render_skeleton(
    meta: SourceMeta, selection: Selection, catalogue: dict[int, str | None]
) -> str:
    """A truth.toml the operator fills in; it asserts nothing by itself.

    `catalogue` maps physical page to the label the file claims for it. Those
    claims appear only as commented hints: the benchmark measures printed
    labels, and a catalogue that is absent, partial or simply wrong must not
    be able to slip into the answer.
    """
    reasons = {t.page: t.reason for t in selection.targeted}
    lines = []
    for physical in selection.all_pages:
        claim = catalogue.get(physical)
        hint = f'catalogue says "{claim}"' if claim else "no catalogue entry"
        note = f" -- {reasons[physical]}" if physical in reasons else ""
        lines.append(f'# "" = {physical}   # {page_stem(physical)}.png, {hint}{note}')
    return _SKELETON_HEAD.format(
        band_id=meta.band_id, bibliography=meta.bibliography,
        license=meta.license, license_class=meta.license_class,
        physical_hints="\n".join(lines) + "\n" if lines else "",
    )


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
    raw = tomllib.loads(raw_toml)
    mapping = {str(k): int(v) for k, v in raw.get("physical_pages", {}).items()}
    want = selection.all_pages
    labelled = set(mapping.values())

    for physical in want:
        if physical not in labelled:
            problems.append(
                f"physical page {physical} was selected but has no printed "
                f"label in [physical_pages]"
            )
    for label, physical in mapping.items():
        if physical not in want:
            problems.append(
                f"label {label!r} maps to physical page {physical}, which was "
                f"never selected"
            )
    for label in truth.pages:
        if label not in mapping:
            problems.append(
                f"label {label!r} is in truth.pages but missing from [physical_pages]"
            )
    for label in mapping:
        if label not in truth.pages:
            problems.append(
                f"label {label!r} is in [physical_pages] but missing from truth.pages"
            )

    empty = {str(p) for p in raw.get("empty_pages", [])}
    with_notes = {f.page for f in truth.footnotes}
    for label in truth.pages:
        if label not in with_notes and label not in empty:
            problems.append(
                f"page {label!r} has no footnote and is not listed in empty_pages"
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
