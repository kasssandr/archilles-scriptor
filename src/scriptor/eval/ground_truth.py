"""Ground truth for one volume: the apparatus as a human verified it.

truth.toml is hand-authored per golden volume. TOML because the standard
library reads it (no new dependency) and multiline German strings stay
legible. Validation is strict: a typo in a status or an unknown page label
must fail loudly at load time, not skew a benchmark silently.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FOOTNOTE_STATUSES = {"intact", "marker_lost", "damaged"}
REGIMES = {"r3", "r4", "none"}


class TruthError(ValueError):
    """truth.toml is malformed or internally inconsistent."""


@dataclass(frozen=True)
class TruthFootnote:
    page: str                       # printed label
    num: int                        # printed, page-local number
    definition_starts: str          # prefix of the definition text (>= ~15 chars)
    status: str                     # intact | marker_lost | damaged
    anchor_after: str | None = None # text immediately before the true anchor; None = position unknown


@dataclass(frozen=True)
class TruthCitation:
    page: str
    text: str                       # verbatim as printed
    regime: str                     # r3 | r4 | none (negative example)
    resolves_to: str | None = None  # bibliography key (r3 only)


@dataclass(frozen=True)
class TruthBibEntry:
    key: str
    raw: str


@dataclass(frozen=True)
class GroundTruth:
    volume: str
    pages: list[str]
    footnotes: list[TruthFootnote] = field(default_factory=list)
    citations: list[TruthCitation] = field(default_factory=list)
    bibliography: list[TruthBibEntry] = field(default_factory=list)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TruthError(msg)


def loads_truth(text: str) -> GroundTruth:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise TruthError(f"not valid TOML: {e}") from e
    _require("volume" in raw and "pages" in raw, "volume and pages are required")
    pages = [str(p) for p in raw["pages"]]
    page_set = set(pages)

    footnotes = []
    for f in raw.get("footnotes", []):
        fn = TruthFootnote(
            page=str(f["page"]), num=int(f["num"]),
            definition_starts=f["definition_starts"], status=f["status"],
            anchor_after=f.get("anchor_after"),
        )
        _require(fn.status in FOOTNOTE_STATUSES, f"unknown status {fn.status!r}")
        _require(fn.page in page_set, f"footnote page {fn.page!r} not in pages")
        footnotes.append(fn)

    citations = []
    for c in raw.get("citations", []):
        cit = TruthCitation(
            page=str(c["page"]), text=c["text"], regime=c["regime"],
            resolves_to=c.get("resolves_to"),
        )
        _require(cit.regime in REGIMES, f"unknown regime {cit.regime!r}")
        _require(cit.page in page_set, f"citation page {cit.page!r} not in pages")
        citations.append(cit)

    bibliography = [TruthBibEntry(key=b["key"], raw=b["raw"])
                    for b in raw.get("bibliography", [])]
    bib_keys = {b.key for b in bibliography}
    for cit in citations:
        if cit.resolves_to is not None:
            _require(cit.resolves_to in bib_keys,
                     f"citation resolves_to {cit.resolves_to!r} has no bibliography entry")
    return GroundTruth(str(raw["volume"]), pages, footnotes, citations, bibliography)


def load_truth(path: Path) -> GroundTruth:
    return loads_truth(Path(path).read_text(encoding="utf-8"))
