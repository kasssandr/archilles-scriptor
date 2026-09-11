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

from scriptor.reflow.regions import REGION_NAMES

FOOTNOTE_STATUSES = {"intact", "marker_lost", "damaged"}
REGIMES = {"r3", "r4", "none"}


class TruthError(ValueError):
    """truth.toml is malformed or internally inconsistent."""


@dataclass(frozen=True)
class TruthFootnote:
    page: str                       # printed label where the note begins
    num: int                        # the number as printed (page-local or running)
    definition_starts: str          # prefix of the definition text (>= ~15 chars)
    status: str                     # intact | marker_lost | damaged
    anchor_after: str | None = None # text immediately before the true anchor; None = position unknown
    # A note may break off at the foot of one page and resume on the next.
    # `page` stays the page it begins on, because that is where the anchor
    # belongs and what every metric keys on. These two record the rest:
    # `definition_ends` makes it checkable whether a converter kept the note
    # whole rather than only finding its opening, and `continues_on` names the
    # page that receives the remainder -- the next page *carrying text*, which
    # is not always the next page.
    definition_ends: str | None = None
    continues_on: str | None = None


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
class TruthRegion:
    """One boundary: from this printed label on, the volume is in `name`.

    Declared for the whole volume rather than for the sampled pages. A
    footnote sample is drawn from body pages and so carries no apparatus at
    all -- keying regions to it would leave the recall question with an empty
    denominator. The boundary therefore need not appear in `pages`, and the
    region reaches to the next boundary, exactly as the marker of spec §4.4
    does.
    """
    from_page: str
    name: str


@dataclass(frozen=True)
class TruthHeading:
    """One heading the volume prints, as its contents and its page give it.

    Declared for the whole volume like a region, and for the same reason: a
    footnote sample carries few headings, and recall needs all of them. The
    entries run in document order, which is what tells two headings with the
    same title apart. `depth` is nesting in the volume's own tree (1 = the
    coarsest level the body is divided on); `designator` is the printed
    numbering verbatim ("A.", "I.", "Erstes Kapitel:"), empty where none is
    printed; `region` names the region the heading opens, if its title names one.
    """
    page: str
    depth: int
    title: str
    designator: str = ""
    region: str | None = None


@dataclass(frozen=True)
class GroundTruth:
    volume: str
    pages: list[str]
    footnotes: list[TruthFootnote] = field(default_factory=list)
    citations: list[TruthCitation] = field(default_factory=list)
    bibliography: list[TruthBibEntry] = field(default_factory=list)
    regions: list[TruthRegion] = field(default_factory=list)
    headings: list[TruthHeading] = field(default_factory=list)
    chapter_level: int | None = None   # the depth the chapters stand on


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
            definition_ends=f.get("definition_ends"),
            continues_on=str(f["continues_on"]) if "continues_on" in f else None,
        )
        _require(fn.status in FOOTNOTE_STATUSES, f"unknown status {fn.status!r}")
        _require(fn.page in page_set, f"footnote page {fn.page!r} not in pages")
        if fn.continues_on is not None:
            _require(fn.continues_on in page_set,
                     f"footnote {fn.num} continues on page {fn.continues_on!r}, "
                     f"which is not in pages -- the receiving page has to be "
                     f"authored too, or the continuation cannot be checked")
            _require(fn.continues_on != fn.page,
                     f"footnote {fn.num} cannot continue on its own page {fn.page!r}")
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

    regions = []
    seen_boundaries: set[str] = set()
    for r in raw.get("regions", []):
        reg = TruthRegion(from_page=str(r["from_page"]), name=r["name"])
        _require(reg.name in REGION_NAMES,
                 f"unknown region name {reg.name!r}; the vocabulary of spec "
                 f"§4.4 is closed: {', '.join(REGION_NAMES)}")
        _require(reg.from_page not in seen_boundaries,
                 f"page {reg.from_page!r} opens a region twice -- one page "
                 f"cannot begin two regions")
        seen_boundaries.add(reg.from_page)
        regions.append(reg)

    bibliography = [TruthBibEntry(key=b["key"], raw=b["raw"])
                    for b in raw.get("bibliography", [])]
    bib_keys = {b.key for b in bibliography}
    for cit in citations:
        if cit.resolves_to is not None:
            _require(cit.resolves_to in bib_keys,
                     f"citation resolves_to {cit.resolves_to!r} has no bibliography entry")
    headings, chapter_level = _headings(raw)
    return GroundTruth(str(raw["volume"]), pages, footnotes, citations,
                       bibliography, regions, headings, chapter_level)


def _headings(raw: dict) -> tuple[list[TruthHeading], int | None]:
    headings = []
    for h in raw.get("headings", []):
        head = TruthHeading(
            page=str(h["page"]), depth=int(h["depth"]), title=h["title"],
            designator=h.get("designator", ""), region=h.get("region"),
        )
        _require(head.depth >= 1,
                 f"heading {head.title!r} on p. {head.page}: depth starts at 1")
        _require(head.title.strip() != "",
                 f"heading on p. {head.page} prints no title")
        _require(head.region is None or head.region in REGION_NAMES,
                 f"heading {head.title!r} opens unknown region {head.region!r}")
        headings.append(head)

    level = raw.get("chapter_level")
    if not headings:
        _require(level is None, "chapter_level is declared but no heading is")
        return headings, None
    _require(level is not None,
             "headings are declared without chapter_level -- the depth the "
             "chapters stand on is part of the division, not a guess")
    level = int(level)
    _require(level in {h.depth for h in headings},
             f"chapter_level {level} is a depth no heading has")
    return headings, level


def load_truth(path: Path) -> GroundTruth:
    return loads_truth(Path(path).read_text(encoding="utf-8"))
