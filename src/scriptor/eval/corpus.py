"""Per-band metadata for the benchmark corpus.

Two hand-written files describe a volume: source.json (where it came from,
under which licence, which checksum) and selection.json (which pages were
chosen, by which method, and why). Both are committed for freely licensed
bands, so both must be strict: a wrong licence class would decide the wrong
storage location, and an undocumented page choice would invite the charge of
cherry-picking.

Selections address pages physically, by their ordinal in the file. The
printed label is what the metrics ultimately measure, but it is a reading of
the page rather than a property the file can be asked for: a PDF catalogue
may be absent, partial, or plainly disagree with the paginated page. So the
selection names PDF pages, and the operator supplies the printed labels in
truth.toml while looking at the page images.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# free       -> truth.toml may be committed
# restricted -> committed, but quoted text kept to citation length
# protected  -> everything lives under golden-local/, gitignored
LICENSE_CLASSES = {"free", "restricted", "protected"}


class CorpusError(ValueError):
    """source.json or selection.json is malformed or inconsistent."""


@dataclass(frozen=True)
class SourceMeta:
    band_id: str
    url: str
    sha256: str
    license: str
    license_class: str
    bibliography: str
    matrix_rows: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class TargetedPage:
    page: int                       # physical page, 1-based file ordinal
    reason: str


@dataclass(frozen=True)
class Selection:
    band_id: str
    seed: int
    body_range: tuple[int, int]
    sampled: list[int] = field(default_factory=list)
    targeted: list[TargetedPage] = field(default_factory=list)

    @property
    def all_pages(self) -> list[int]:
        """Every physical page the operator has to author, sampled first."""
        return list(self.sampled) + [t.page for t in self.targeted]


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise CorpusError(msg)


def loads_source(text: str) -> SourceMeta:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise CorpusError(f"not valid JSON: {e}") from e
    for key in ("band_id", "url", "sha256", "license", "license_class", "bibliography"):
        _require(bool(str(raw.get(key, "")).strip()), f"{key} is required and must not be empty")
    cls = raw["license_class"]
    _require(cls in LICENSE_CLASSES, f"unknown license_class {cls!r}")
    digest = str(raw["sha256"]).lower()
    _require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
             "sha256 must be 64 hex characters")
    rows = [int(r) for r in raw.get("matrix_rows", [])]
    return SourceMeta(
        band_id=str(raw["band_id"]), url=str(raw["url"]), sha256=digest,
        license=str(raw["license"]), license_class=cls,
        bibliography=str(raw["bibliography"]), matrix_rows=rows,
    )


def loads_selection(text: str) -> Selection:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise CorpusError(f"not valid JSON: {e}") from e
    _require("band_id" in raw and "seed" in raw, "band_id and seed are required")
    body = raw.get("body_range")
    _require(isinstance(body, list) and len(body) == 2,
             "body_range must be a two-element list of physical page numbers")
    first, last = int(body[0]), int(body[1])
    _require(0 < first <= last, "body_range must be ascending and 1-based")

    sampled = [int(p) for p in raw.get("sampled", [])]
    targeted = []
    for t in raw.get("targeted", []):
        _require("page" in t, "a targeted page needs a physical page number")
        page, reason = int(t["page"]), str(t.get("reason", "")).strip()
        _require(bool(reason), f"targeted page {page} needs a reason in plain words")
        targeted.append(TargetedPage(page=page, reason=reason))

    seen = sampled + [t.page for t in targeted]
    for page in seen:
        _require(first <= page <= last,
                 f"selected page {page} lies outside the body range {first}-{last}")
    _require(len(seen) == len(set(seen)), "a page must not be selected twice")
    return Selection(str(raw["band_id"]), int(raw["seed"]), (first, last),
                     sampled, targeted)


def load_source(path: Path) -> SourceMeta:
    return loads_source(Path(path).read_text(encoding="utf-8"))


def load_selection(path: Path) -> Selection:
    return loads_selection(Path(path).read_text(encoding="utf-8"))


def band_root(meta: SourceMeta, corpus_dir: Path, local_dir: Path) -> Path:
    """Where everything about this band lives.

    Protected bands never appear under the committed corpus directory — not
    their truth, not even their metadata.
    """
    base = local_dir if meta.license_class == "protected" else corpus_dir
    return Path(base) / meta.band_id
