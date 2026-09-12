"""The division of a volume: one model for the PDF, the EPUB and the master.

A volume divides itself into a tree of printed headings. Each heading is a
node with a depth in *this* volume's tree, the designator it prints ("A.",
"II.", "Erstes Kapitel:"), the scheme that designator belongs to, its title,
where it stands and who testified to it (Gliederungsmodell §3.1). Depth is
nesting, not rank: which depth carries the chapters is a property of the
volume, declared by :meth:`Tree.chapter_level`, never read off a '#'.

Three producers build such trees -- Scriptor from the pages, Archilles from
an EPUB's nav, and anyone from a master's '#' lines -- and one function,
:meth:`Tree.fields_of`, turns a node into the ``chapter`` / ``section_title``
/ ``section`` a consumer stores. That the three paths share it is the point
of the module.

Pure functions and small data classes. Nothing here reads a page, and nothing
here imports from ``reflow``: the direction is ``reflow -> structure``. Where
a rule needs to know which region a title names, the caller passes that in.

The numbering rules were measured before they were written (Briefing G6,
``docs/internal/gliederung-2026-09/G6_schemes.md``). The stack of Befund
§5.3 got 7 of Bauer's 178 contents depths right; with the three amendments
in :func:`learn_schemes` it gets 169, and the remaining nine are entries the
contents parser lost. Against eight outlines the amended rules keep 128 of
146 changes of level, the plain stack 103.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from scriptor.languages import NOT_ATTESTED

# The version of the structure sidecar (spec §6.5). A reader refuses any other.
SIDECAR_VERSION = 1

# ATX headings have six levels, and so has HTML. A deeper node is written with
# six, and its true depth travels in the sidecar (Briefing §8.3).
MAX_MARKDOWN_DEPTH = 6

# ── word forms ─────────────────────────────────────────────────────────
#
# A catalogue, like the region vocabulary: a language answers with patterns
# attested in the corpus, or with NOT_ATTESTED. A missing word yields an
# unnumbered entry, which is the safe direction -- it is never mistaken for a
# number of another scheme.

_ROMAN_OR_NUMBER = r"(?:[IVXLC]+|\d+|[A-Z]|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"

CHAPTER_WORDS: dict[str, tuple[str, ...] | object] = {
    # Bauer prints "Erstes Kapitel:" to "Fünftes Kapitel:".
    "de": (r"(?:erstes|zweites|drittes|viertes|fünftes|sechstes|siebtes|siebentes|"
           r"achtes|neuntes|zehntes|elftes|zwölftes)\s+kapitel",),
    # Chaldaean Oracles: "CHAPTER I."
    "en": (rf"chapter\s+{_ROMAN_OR_NUMBER}",),
    # L'Empire chrétien, Les apologistes grecs: "CHAPITRE III. -"
    "fr": (rf"chapitre\s+{_ROMAN_OR_NUMBER}",),
    # Masones, La masonería, Libros de no poco sobresalto: "Capítulo IV."
    "es": (rf"cap[íi]tulo\s+{_ROMAN_OR_NUMBER}",),
    # De eerste minister: "Hoofdstuk 1 -"
    "nl": (rf"hoofdstuk\s+{_ROMAN_OR_NUMBER}",),
    # Militarizing Men: "Глава 1."
    "ru": (rf"глава\s+{_ROMAN_OR_NUMBER}",),
    # Italian would print "Capitolo 3", Portuguese "Capítulo 3"; no contents
    # page in the corpus shows either, and Latin none at all.
    "it": NOT_ATTESTED,
    "pt": NOT_ATTESTED,
    "la": NOT_ATTESTED,
}

PART_WORDS: dict[str, tuple[str, ...] | object] = {
    # 10588 and 9205: "TEIL 1:", "Teil C:". The ordinal form follows Bauer's
    # "Erstes Kapitel", the same grammar one word further up.
    "de": (r"(?:erster|zweiter|dritter|vierter|fünfter|sechster|siebter|achter|neunter|zehnter)\s+teil",
           rf"teil\s+{_ROMAN_OR_NUMBER}"),
    # 1136 and 9498: "PART I:"
    "en": (rf"part\s+{_ROMAN_OR_NUMBER}",),
    # Pouderon, Les apologistes grecs: "PREMIÈRE PARTIE"
    "fr": (r"(?:premi[èe]re|deuxi[èe]me|troisi[èe]me|quatri[èe]me|cinqui[èe]me)\s+partie",),
    "it": NOT_ATTESTED,
    "es": NOT_ATTESTED,
    "pt": NOT_ATTESTED,
    "nl": NOT_ATTESTED,
    "ru": NOT_ATTESTED,
    "la": NOT_ATTESTED,
}


def _word_pattern(catalogue: dict) -> re.Pattern:
    words = [p for entry in catalogue.values() if entry is not NOT_ATTESTED for p in entry]
    return re.compile(rf"(?i)^(?:{'|'.join(words)})\b[\s.:–—-]*")


# ── schemes ────────────────────────────────────────────────────────────
#
# The forms a designator takes, first match wins. The order matters twice:
# doubled letters before single ones ("aa)" is not "a)"), and letters with a
# parenthesis before lower-case roman numerals ("c)" is a letter, "cc)" too).
# A dotted number is one scheme per number of parts, so that the stack keeps
# "1.1" and "1.1.1" apart -- the scheme carries its depth itself (Befund §5.3,
# Sen et al.).

WORD_SCHEMES = ("word-part", "word-ordinal")

SCHEMES: tuple[tuple[str, re.Pattern], ...] = (
    ("word-ordinal", _word_pattern(CHAPTER_WORDS)),
    ("word-part", _word_pattern(PART_WORDS)),
    ("section-sign", re.compile(r"^§\s*\d+[a-z]?(?:\.\d+)*\.?\s+")),
    ("arabic-dotted-4", re.compile(r"^\d+\.\d+\.\d+\.\d+\.?\s+")),
    ("arabic-dotted-3", re.compile(r"^\d+\.\d+\.\d+\.?\s+")),
    ("arabic-dotted-2", re.compile(r"^\d+\.\d+\.?\s+")),
    ("arabic", re.compile(r"^\d{1,3}\.\s+")),
    ("arabic-paren", re.compile(r"^\d{1,3}\)\s+")),
    ("paren-arabic", re.compile(r"^\(\d{1,3}\)\s+")),
    ("roman-upper", re.compile(r"^[IVXLC]{1,7}[.)]\s*")),
    ("roman-upper-bare", re.compile(r"^[IVXLC]{2,7}\s+(?=[\w„\"«(])")),
    ("letter-double-paren", re.compile(r"^([a-z])\1\)\s+")),
    ("letter-lower-paren", re.compile(r"^[a-z]\)\s+")),
    ("roman-lower", re.compile(r"^[ivxlc]{2,7}[.)]\s+|^i\.\s+")),
    ("letter-upper", re.compile(r"^[A-Z]\.\s+")),
    ("letter-upper-paren", re.compile(r"^[A-Z]\)\s+")),
    ("paren-letter", re.compile(r"^\([a-z]\)\s+")),
    ("letter-lower-dot", re.compile(r"^[a-z]\.\s+")),
    ("bullet", re.compile(r"^[•▪◦‣*·]\s*")),
    ("arabic-bare", re.compile(r"^\d{1,3}\s+(?=[A-ZÀ-ÝА-Я„\"«])")),
)

# A lone capital that is also a roman numeral. L, C, D and M are not among
# them: no volume numbers a section 50 or 100, and Bauer's "C. Eingriff …" is
# the third section of a chapter that also prints "I." and "II.".
_LONE_ROMAN = frozenset("IVX")

# "II.1", "2.3.1.": an entry that numbers itself below a top level. The same
# test as reflow.chapters._SUBSECTION, on the designator.
_SUBSECTION = re.compile(r"^\s*(?:[IVXLCivxlc]+|\d{1,3})\s*\.\s*\d")


def scheme_of(text: str, roman_volume: bool) -> tuple[str, str, str]:
    """(scheme, designator, title) of a heading as printed; ('', '', text)
    for an unnumbered one.

    ``roman_volume`` says whether the volume prints roman numerals of two
    letters or more anywhere; only then is a lone I, V or X a numeral rather
    than a letter.
    """
    t = text.strip()
    for name, rx in SCHEMES:
        m = rx.match(t)
        if not m:
            continue
        designator = m.group(0).strip()
        title = t[m.end():].strip()
        lone = designator.rstrip(".)")
        if name == "roman-upper" and len(lone) == 1 and (
                not roman_volume or lone not in _LONE_ROMAN):
            name = "letter-upper" if designator.endswith(".") else "letter-upper-paren"
        return name, designator, title
    return "", "", t


def is_roman_volume(texts: Iterable[str]) -> bool:
    """Does the volume print a roman numeral of two letters or more?"""
    return any(re.match(r"^\s*[IVXLC]{2,7}[.)\s]", t) for t in texts)


# ── packaging ──────────────────────────────────────────────────────────
#
# What the binder wrapped around the book. Not a part of its division, so
# never a node, and a level made of nothing else is not the chapter level.
# Measured on level 1 of the corpus outlines: "Cover" and "Half Title"
# (Oxford Handbook), "Cubierta" and "Portada" (Libros), "Cover" (Asclepios,
# Libros, bauer-aneignung, De eerste minister), and at mehr-themistios the
# bare ISBN, twice. The rest are the immediate neighbours of those in the
# corpus languages. reflow.chapters takes its list from here.
PACKAGING_WORDS = re.compile(
    r"^(?:"
    r"front\s*cover|back\s*cover|cover|half[-\s]*title|title\s*page|"
    r"umschlag|schutzumschlag|titelblatt|titelei|impressum|kolophon|"
    r"omslag|voorplat|achterplat|titelpagina|colofon|"
    r"cubierta|portada|portadilla|colof[óo]n|cr[ée]ditos|"
    r"copertina|frontespizio|colophon|couverture|page\s*de\s*titre|"
    r"capa|folha\s*de\s*rosto|ficha\s*t[ée]cnica"
    r")$|^\d[\d\s-]{6,}$",   # ... and a bare ISBN is not a title at all
    re.IGNORECASE,
)


def is_packaging(title: str) -> bool:
    return bool(PACKAGING_WORDS.match(title.strip()))


# ── epub:type → region (Befund, Anhang B1) ─────────────────────────────
#
# A type that marks an *element* (a footnote, an index entry) is not a
# region; a partition type without a finer one names none either --
# `frontmatter` holds prefaces, `backmatter` afterwords. A type missing from
# the table names no region: unknown is running text.
EPUB_TYPE_REGIONS: dict[str, str | None] = {
    **dict.fromkeys(("cover", "titlepage", "halftitlepage", "copyright-page", "imprint",
                     "dedication", "colophon"), "front-matter"),
    "toc": "contents",
    **dict.fromkeys(("loi", "lot"), None),
    **dict.fromkeys(("preface", "foreword", "acknowledgments"), "preface"),
    **dict.fromkeys(("introduction", "prologue", "epigraph", "preamble"), None),
    **dict.fromkeys(("bodymatter", "part", "chapter", "subchapter", "division", "volume",
                     "conclusion", "epilogue", "afterword"), None),
    "bibliography": "bibliography",
    "index": "index",
    **dict.fromkeys(("endnotes", "rearnotes", "footnotes"), "notes"),
    "appendix": "appendix",
    "glossary": None,
    **dict.fromkeys(("frontmatter", "backmatter"), None),
    **dict.fromkeys(("footnote", "noteref", "rearnote", "biblioentry", "index-entry-list",
                     "landmarks", "page-list", "pagebreak", "errata", "contributors",
                     "other-credits", "notice", "warning", "qna", "abstract", "keywords",
                     "list"), None),
}


def region_for_epub_type(types: str | Iterable[str]) -> str | None:
    """The region an element's ``epub:type`` names, or None.

    ``epub:type`` is a space-separated list; the first type that names a
    region wins ("backmatter bibliography" -> bibliography).
    """
    items = types.split() if isinstance(types, str) else list(types)
    for t in items:
        region = EPUB_TYPE_REGIONS.get(t.strip().lower())
        if region:
            return region
    return None


# ── the model ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Witness:
    """Who placed a node, and why. The vocabulary of ``source`` grows like
    the pagination's (spec §6.5): contents, outline, numbering, typography,
    running-head; nav, heading-tag, epub-type. Unknown values pass through."""
    source: str
    why: str = ""


@dataclass
class Node:
    depth: int
    title: str
    designator: str = ""
    scheme: str = ""
    page: str | None = None      # the printed label (PDF)
    pos: int | None = None       # the physical page (PDF)
    anchor: str | None = None    # file#anchor (EPUB)
    sources: list[Witness] = field(default_factory=list)
    region: str | None = None    # the region this node opens, if its title names one

    @property
    def text(self) -> str:
        """The heading as printed: designator and title."""
        return f"{self.designator} {self.title}".strip()


@dataclass(frozen=True)
class SchemeRow:
    scheme: str
    depth: int
    count: int


@dataclass
class SchemeTable:
    """scheme -> depth, as one volume uses it, in the order of depth."""
    rows: list[SchemeRow]

    def depth_of(self, scheme: str) -> int | None:
        return next((r.depth for r in self.rows if r.scheme == scheme), None)

    def scheme_at(self, depth: int) -> str | None:
        return next((r.scheme for r in self.rows if r.depth == depth), None)


@dataclass(frozen=True)
class Entry:
    """A contents entry as the producer read it."""
    text: str                    # designator and title, as printed
    page: str | int | None = None
    indent: float | None = None  # from the left edge of its page
    region: str | None = None    # the region its title names, if any


@dataclass
class Learnt:
    table: SchemeTable
    depths: list[int]            # one per entry, in reading order
    schemes: list[str]           # one per entry; '' for unnumbered


_TOP = "(top)"


def learn_schemes(entries: Sequence[Entry]) -> Learnt:
    """The scheme table of a volume, learnt from the order of its contents.

    The stack of Befund §5.3 -- a scheme already on the stack closes what
    lies above it, a new one goes on top -- with three amendments, each
    measured in G6:

    1. **The top.** An unnumbered entry before the first numbered one, one
       whose title names a region, or one at the left edge of its page (where
       the volume indents at all) is depth 1 and clears the stack. The
       numbered entry after it is its child if it starts on the same page or
       is indented deeper -- Bauer's 'Einleitung' 19 › 'A. Problemaufriss' 19
       -- and its sibling otherwise ('Introduction' 1, 'I.' 9).
    2. **Word forms.** A part clears the stack; a chapter clears it down to a
       part. Otherwise 'Erstes Kapitel' after 'Einleitung › A.' lands on 3.
    3. **Other unnumbered entries** are sections of a word form directly above
       them (De eerste minister: flush-left sections under 'Hoofdstuk'), and
       siblings of the last numbered entry otherwise ('Conclusion' after
       '2.'). The Befund's 'depth of the entry before' kept 112 of 146 changes
       of level against the outlines, this 128.

    The table gives each scheme the depth most of its entries stand on: one
    lost contents line can make an 'a)' jump a level, the table does not.
    """
    roman = is_roman_volume(e.text for e in entries)
    parsed = [scheme_of(e.text, roman) for e in entries]
    indents_used = any(s and (e.indent or 0) > 5 for e, (s, _, _) in zip(entries, parsed))

    stack: list[str] = []
    depths: list[int] = []
    top: Entry | None = None
    seen_numbered = False
    last_numbered, last_word = 0, False
    for e, (s, _, _) in zip(entries, parsed):
        if not s:
            at_top = (not seen_numbered or e.region is not None
                      or (indents_used and e.indent is not None and e.indent <= 2.0))
            if at_top:
                stack, top = [_TOP], e
                depths.append(1)
            else:
                depths.append(last_numbered + 1 if last_word else max(last_numbered, 1))
            continue
        seen_numbered = True
        if stack == [_TOP] and s not in WORD_SCHEMES:
            child = (top is not None and top.page is not None
                     and str(e.page) == str(top.page)) or (
                top is not None and e.indent is not None and top.indent is not None
                and e.indent > top.indent + 5)
            if not child:
                stack = []
        if s in WORD_SCHEMES and s not in stack:
            parts = [x for x in stack if x == "word-part"] if s == "word-ordinal" else []
            stack = parts + [s]
        elif s in stack:
            del stack[stack.index(s) + 1:]
        else:
            stack.append(s)
        depths.append(stack.index(s) + 1)
        last_numbered, last_word = depths[-1], s in WORD_SCHEMES

    by_scheme: dict[str, Counter] = {}
    first_seen: dict[str, int] = {}
    for k, ((s, _, _), d) in enumerate(zip(parsed, depths)):
        if s:
            by_scheme.setdefault(s, Counter())[d] += 1
            first_seen.setdefault(s, k)
    rows = [SchemeRow(s, c.most_common(1)[0][0], sum(c.values())) for s, c in by_scheme.items()]
    rows.sort(key=lambda r: (r.depth, first_seen[r.scheme]))
    return Learnt(SchemeTable(rows), depths, [s for s, _, _ in parsed])


@dataclass(frozen=True)
class Fields:
    chapter: str
    section_title: str
    section: str


@dataclass
class Tree:
    """The headings of a volume in document order. Depth may jump."""
    nodes: list[Node]

    @classmethod
    def from_headings(cls, headings: Iterable[tuple[int, str]],
                      region_of: Callable[[str], str | None] | None = None) -> "Tree":
        """A tree from (depth, heading text) pairs -- a master's '#' lines.

        The text is the heading as printed; one emphasis around the whole of
        it is typography (Briefing §8.3) and goes. ``region_of`` names the
        region a title opens (reflow.regions.region_of_heading, passed in by
        the caller so that this module imports nothing from reflow).
        """
        rows = [(d, strip_heading_emphasis(t.strip())) for d, t in headings]
        roman = is_roman_volume(t for _, t in rows)
        nodes = []
        for depth, text in rows:
            scheme, designator, title = scheme_of(text, roman)
            nodes.append(Node(depth=depth, title=title, designator=designator, scheme=scheme,
                              region=region_of(text) if region_of else None))
        return cls(nodes)

    def ancestors(self, i: int) -> list[int]:
        """The indices of node i's ancestors, nearest first."""
        out, depth = [], self.nodes[i].depth
        for j in range(i - 1, -1, -1):
            if self.nodes[j].depth < depth:
                out.append(j)
                depth = self.nodes[j].depth
        return out

    def chapter_level(self) -> int | None:
        """The depth on which this volume opens its chapters (Befund §3.2).

        1. A level whose nodes are all packaging, region heads, or numbered
           below a top level ("II.1") is not the chapter level.
        2. A level holding a part lies above the chapter level.
        3. Of the levels left, the coarsest with at least two body nodes --
           region heads and packaging do not count towards the two -- else the
           coarsest with one, else the level with the most nodes.
        """
        if not self.nodes:
            return None
        levels: dict[int, list[Node]] = {}
        for n in self.nodes:
            levels.setdefault(n.depth, []).append(n)

        def body(n: Node) -> bool:
            return not (is_packaging(n.title) or is_packaging(n.text) or n.region
                        or n.scheme.startswith("arabic-dotted") or _SUBSECTION.match(n.designator))

        excluded = {d for d, ns in levels.items() if not any(body(n) for n in ns)}
        parts = [d for d, ns in levels.items() if any(n.scheme == "word-part" for n in ns)]
        floor = max(parts) if parts else 0
        left = [d for d in sorted(levels) if d > floor and d not in excluded]
        for need in (2, 1):
            for d in left:
                if sum(1 for n in levels[d] if body(n)) >= need:
                    return d
        return max(levels, key=lambda d: len(levels[d]))

    def fields_of(self, i: int, chapter_level: int | None = None) -> Fields:
        """``chapter``, ``section_title`` and ``section`` of node i.

        ``chapter`` is the ancestor-or-self on the chapter level, or the
        nearest one above it where the tree jumps; a node above the chapter
        level (an introduction beside parts) is its own chapter.
        ``section_title`` is the node itself where it lies deeper than the
        chapter level. ``section`` is the chain of designators below the
        chapter, without word forms: "A.II.1".
        """
        level = chapter_level if chapter_level is not None else (self.chapter_level() or 1)
        node = self.nodes[i]
        chain = [i] + self.ancestors(i)
        chapter = next((self.nodes[j] for j in chain if self.nodes[j].depth <= level), node)
        if node.depth <= level:
            return Fields(node.text, "", "")
        below = [self.nodes[j] for j in reversed(chain) if self.nodes[j].depth > level]
        section = ".".join(_designator_key(n.designator) for n in below
                           if n.designator and n.scheme not in WORD_SCHEMES)
        return Fields(chapter.text if chapter.depth <= level else "", node.text, section)


def _designator_key(designator: str) -> str:
    return designator.strip().strip("()").rstrip(".):-– ").strip()


# ── the master line ────────────────────────────────────────────────────

_EMPHASIS = re.compile(r"^([*_])([^*_].*?)\1$")


def strip_heading_emphasis(text: str) -> str:
    """The heading text without one emphasis around the whole of it."""
    m = _EMPHASIS.match(text.strip())
    if m and m.group(1) not in m.group(2):
        return m.group(2)
    return text


def heading_markdown(node: Node, table: SchemeTable) -> str:
    """The master line for a node (Briefing §8.3).

    Depths 1 to 6 are '#' to '######'. A deeper node is '######' too; where
    its printed designator tells it from depth 6 that is enough, and where the
    print does not -- no scheme, or the scheme of depth 6 -- its text is set in
    emphasis. Its true depth travels in the sidecar either way.
    """
    hashes = "#" * min(node.depth, MAX_MARKDOWN_DEPTH)
    text = node.text
    if node.depth > MAX_MARKDOWN_DEPTH and (not node.scheme
                                            or node.scheme == table.scheme_at(MAX_MARKDOWN_DEPTH)):
        text = f"*{text}*"
    return f"{hashes} {text}"


# ── the sidecar (spec §6.5) ────────────────────────────────────────────

@dataclass
class Structure:
    """One reading of a volume's division, as the sidecar carries it."""
    chapter_level: int | None
    schemes: SchemeTable
    headings: list[Node]
    unplaced: list[dict] = field(default_factory=list)   # contents entries found on no page
    rejected: list[dict] = field(default_factory=list)   # lines declined, each with its reason
    version: int = SIDECAR_VERSION


def describe(structure: Structure) -> str:
    """The metadata block's ``structure:`` line: one line, to be read."""
    depths = {n.depth for n in structure.headings}
    first = Counter(n.sources[0].source for n in structure.headings if n.sources)
    by_source = ", ".join(f"{k} {s}" for s, k in first.most_common())
    return (f"{len(depths)} levels, chapters on level {structure.chapter_level}, "
            f"{len(structure.headings)} headings" + (f" ({by_source})" if by_source else ""))


def _node_json(n: Node) -> dict:
    return {"depth": n.depth, "designator": n.designator, "scheme": n.scheme, "title": n.title,
            "page": n.page, "pos": n.pos, "anchor": n.anchor,
            "sources": [{"source": w.source, "why": w.why} for w in n.sources],
            "region": n.region}


def render_structure_sidecar(structure: Structure, name: str) -> tuple[str, str]:
    """(json, txt) for ``<name>.structure.json`` / ``.txt``. Stable JSON, so a
    rerun that changes nothing produces no diff."""
    payload = {
        "version": structure.version,
        "chapter_level": structure.chapter_level,
        "schemes": [{"scheme": r.scheme, "depth": r.depth, "count": r.count}
                    for r in structure.schemes.rows],
        "headings": [_node_json(n) for n in structure.headings],
        "unplaced": structure.unplaced,
        "rejected": structure.rejected,
    }
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"

    lines = [f"# Structure of {name}",
             f"# {describe(structure)}.",
             "# Sources: contents = the contents entry's title was found on its page,",
             "# outline = the PDF's bookmarks, numbering = the scheme table placed it,",
             "# typography = size or weight, running-head = the head of a later page;",
             "# nav, heading-tag, epub-type = the EPUB's own structure.",
             "", "## Tree"]
    for n in structure.headings:
        where = f"p. {n.page}" if n.page is not None else (n.anchor or "")
        src = ", ".join(w.source for w in n.sources)
        region = f"  [region: {n.region}]" if n.region else ""
        lines.append(f"{'  ' * (n.depth - 1)}{n.text}  — {where}  ({src}){region}".rstrip())
    lines += ["", "## Schemes"]
    lines += [f"  depth {r.depth}  {r.scheme or '(unnumbered)'}  ×{r.count}"
              for r in structure.schemes.rows] or ["  none"]
    lines += ["", f"## Contents entries found on no page: {len(structure.unplaced)}"]
    lines += [f"  p. {u.get('page')}  {u.get('text')}" for u in structure.unplaced]
    lines += ["", f"## Lines declined as headings: {len(structure.rejected)}"]
    lines += [f"  p. {r.get('page')}  {r.get('text')}  — {r.get('reason')}"
              for r in structure.rejected]
    return text, "\n".join(lines) + "\n"


def read_structure_sidecar(master: str | Path) -> Structure | None:
    """The structure sidecar next to ``master``, or None where there is none.

    A sidecar of another version is refused, not half-read. Sources the
    reader does not know are carried through (spec §6.5).
    """
    path = Path(master)
    path = path.with_name(path.name + ".structure.json")
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = payload.get("version")
    if version != SIDECAR_VERSION:
        raise ValueError(f"{path.name}: structure sidecar version {version!r}, "
                         f"this reader knows {SIDECAR_VERSION}")
    return Structure(
        chapter_level=payload.get("chapter_level"),
        schemes=SchemeTable([SchemeRow(r["scheme"], r["depth"], r["count"])
                             for r in payload.get("schemes", [])]),
        headings=[Node(depth=h["depth"], title=h["title"], designator=h.get("designator", ""),
                       scheme=h.get("scheme", ""), page=h.get("page"), pos=h.get("pos"),
                       anchor=h.get("anchor"),
                       sources=[Witness(w["source"], w.get("why", "")) for w in h.get("sources", [])],
                       region=h.get("region"))
                  for h in payload.get("headings", [])],
        unplaced=payload.get("unplaced", []),
        rejected=payload.get("rejected", []),
        version=version,
    )
