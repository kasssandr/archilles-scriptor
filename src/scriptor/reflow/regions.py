"""Structural regions of PREPARED_FORMAT_SPEC §4.4.

The producer knows more about a volume's structure than a consumer can
recover from the text, and until now it kept that knowledge to itself:
``assign_modes`` decided how a page is *set* and threw the reason away. This
module names the region instead, so a retrieval consumer can exclude an index
without recognising one.

Two things are deliberately apart here, as they are in the spec: the
**treatment** (``Page.mode`` — reflow prose, keep lines, render a TOC) stays
where it was, and the **name** (``Page.region``) is new. A bibliography set by
a publisher who indents nothing is still a bibliography.

The closing rule carries the weight. An opening heading is cheap to find and
easy to find wrongly — *Abkürzungen:* occurs mid-essay — and a region that
never closes turns the rest of the volume into apparatus. That is the failure
§4.4 calls silent loss, so every rule here is biased the same way: when the
evidence thins out, the region ends and the text is running text again.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

# The version of PREPARED_FORMAT_SPEC this producer writes. Stated in the
# document itself (§4.1), because a prepared document outlives the release
# notes that describe it.
FORMAT_VERSION = "0.2.0"

# The marker of §4.4, on a line of its own.
REGION_MARKER = "[region: {name}]"

# The closed vocabulary of §4.4. Order is meaningless; membership is not.
REGION_NAMES = (
    "front-matter",
    "contents",
    "main",
    "bibliography",
    "index",
    "abbreviations",
    "notes",
    "appendix",
)

# Regions that name an apparatus — the ones a retrieval consumer wants to
# exclude.
APPARATUS = ("bibliography", "index", "abbreviations", "notes", "appendix")

# Regions the closing rules apply to. A table of contents is not apparatus,
# but it must close like one: a volume that prints its contents at the end
# (Pückert 1899, Guilhiermoz 1902) would otherwise carry `contents` over every
# chapter that follows, which is the same silent loss by another name.
_CLOSEABLE = APPARATUS + ("contents",)

# Heading vocabulary. One list per region, matched against a whole heading
# line, case- and accent-insensitively (an OCR layer drops diacritics often
# enough that requiring them would cost more than it protects).
#
# Languages: German, English, French, Italian, Spanish, Portuguese, Dutch,
# Latin (scholarly editions title their indices in it) and Russian. Adding a
# language is adding entries here — the matching rule below stays untouched.
# CJK is out: these patterns key on word boundaries, which do not carry there.
_VOCABULARY: dict[str, tuple[str, ...]] = {
    "bibliography": (
        # de — "Quellen- und Literaturverzeichnis" too, hence the optional lead
        r"(?:quellen[-\s–]*und[-\s]*)?literatur(?:verzeichnis|nachweis)?",
        r"(?:quellen|siglen)?(?:verzeichnis)?[-\s]*bibliographie",
        r"bibliographie", r"bibliografie",
        r"quellenverzeichnis", r"quellen und literatur",
        r"verzeichnis der (?:zitierten |verwendeten )?literatur",
        # en
        r"(?:select(?:ed)?\s+|primary\s+|secondary\s+|general\s+)?bibliography",
        r"works cited", r"list of works", r"references",
        r"(?:list of |primary |printed )?sources",
        # fr
        r"bibliographie(?: s[ée]lective| g[ée]n[ée]rale)?",
        r"r[ée]f[ée]rences(?: bibliographiques)?",
        r"sources(?: et bibliographie)?",
        # it / es / pt
        r"bibliografia", r"bibliograf[íi]a",
        r"fonti(?: e bibliografia)?", r"riferimenti bibliografici",
        r"obras citadas", r"refer[êe]ncias(?: bibliogr[áa]ficas)?",
        # nl
        r"bibliografie", r"literatuur(?:lijst|opgave)?", r"geraadpleegde werken",
        # la
        r"bibliographia", r"conspectus librorum",
        # ru
        r"библиография", r"список литературы", r"литература",
        r"источники(?: и литература)?",
    ),
    "index": (
        # de — Personen-, Sach-, Orts-, Namen-, Stellen-, Autoren-, Bibelstellen-
        r"(?:\w+[-\s]?)?register",
        r"(?:namen|orts|personen|sach|stellen)verzeichnis",
        r"index(?: der \w+)?",
        # en
        r"(?:general |subject |name |author |place |scriptural )?index(?:es)?",
        r"indices", r"index of (?:names|subjects|places|persons|passages)",
        # fr
        r"index(?: des \w+| g[ée]n[ée]ral| nominum)?", r"table onomastique",
        # it / es / pt
        r"indice(?: dei nomi| analitico| generale)?",
        r"[íi]ndice(?: de \w+| onom[áa]stico| anal[íi]tico)?",
        r"[íi]ndice remissivo",
        # nl
        r"register(?: van \w+)?", r"zaakregister", r"namenregister",
        # la
        r"index (?:nominum|rerum|locorum|verborum|auctorum)",
        # ru
        r"указатель(?: имён| имен| названий)?", r"именной указатель",
        r"предметный указатель",
    ),
    "abbreviations": (
        # de
        r"abk[üu]rzungs(?:verzeichnis|liste)?", r"abk[üu]rzungen",
        r"siglen(?:verzeichnis)?", r"verzeichnis der abk[üu]rzungen",
        # en
        r"(?:list of |table of )?abbreviations", r"sigla", r"short titles",
        # fr
        r"abr[ée]viations(?: et sigles)?", r"liste des abr[ée]viations", r"sigles",
        # it / es / pt
        r"abbreviazioni", r"abreviaturas", r"siglas(?: e abreviaturas)?",
        # nl
        r"afkortingen(?:lijst)?", r"lijst van afkortingen",
        # la
        r"index siglorum", r"sigla",
        # ru
        r"список сокращений", r"сокращения", r"условные обозначения",
    ),
    "contents": (
        # A table of contents at the *end* of a volume — Guilhiermoz 1902 and
        # Pückert 1899 both put it there. assign_modes only reaches the ones it
        # meets while still in front matter, so the region needs its own words.
        r"inhalts(?:verzeichnis|[üu]bersicht|angabe)?", r"inhalt",
        r"(?:table of )?contents", r"table des mati[èe]res", r"sommaire",
        r"indice generale", r"[íi]ndice general", r"sum[áa]rio",
        r"inhoud(?:sopgave)?", r"оглавление", r"содержание",
    ),
    "notes": (
        # A collected notes section, as distinct from the footnotes of §4.3.
        r"anmerkungen", r"endnoten", r"anmerkungsapparat",
        # Plural only. A volume that heads a page "NOTE" is nearly always
        # making a publisher's remark, not opening an apparatus — Baynes does
        # exactly that on its imprint page.
        r"notes", r"endnotes", r"reference notes",
        r"notas", r"noten", r"adnotationes",
        r"примечания", r"комментарии",
    ),
    "appendix": (
        r"anh[äa]nge?", r"anlagen?", r"beilagen?", r"tabellenanhang",
        r"appendix(?:\s+[ivxlcdm]+|\s+\d+|\s+[a-z])?", r"appendices",
        r"annexes?", r"appendice", r"ap[êe]ndices?", r"ap[ée]ndices?",
        r"bijlagen?",
        r"приложения?",
    ),
}

# An optional ordinal in front of the title: "13.", "IV.", "A.", "§ 3".
_PREFIX = r"(?:(?:§\s*)?(?:\d{1,3}|[ivxlcdm]{1,6}|[a-z])[.)]?\s+)?"

# A heading is short. Beyond this the line is prose that happens to open with
# the word, and prose is never a region marker.
_MAX_HEADING_CHARS = 48

def _fold(text: str) -> str:
    """Lowercase and strip diacritics, so 'Índice' matches 'indice'.

    Applied to the patterns as well as to the line, or the two would disagree
    exactly where it matters: NFD decomposes Russian 'ё' into 'е' plus a
    combining mark, so a pattern written 'имён' would never meet a folded
    'имен'.
    """
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# What may trail a heading: a closing stop or colon, because older typography
# sets headings that way ("Inhaltsübersicht.", Pückert 1899) — and the marks a
# scan turns those into. Guilhiermoz's running head arrives as "INDEX
# ALPHABÉTIQUE ·", its printed full stop read back as a middle dot; refusing
# it costs nine pages of index. Tolerating the tail costs nothing, because
# what precedes it still has to be a whole vocabulary word: no sentence
# becomes a heading by ending in a period.
_TRAILING = r"[.,:;·•∙]?"

_COMPILED: dict[str, tuple[re.Pattern[str], ...]] = {
    region: tuple(
        re.compile(_fold(rf"^{_PREFIX}{alt}\s*{_TRAILING}\s*$"), re.IGNORECASE)
        for alt in alternatives
    )
    for region, alternatives in _VOCABULARY.items()
}


# A title-like complement after the region word: INDEX ALPHABÉTIQUE, INDEX DES
# NOMS DE PERSONNES, ÍNDICE DE NOMBRES PROPIOS. Only tried on lines set in
# capitals — which is how volumes actually print these — because the pattern is
# otherwise wide enough to swallow a sentence that opens with the word.
_CAPITALISED: dict[str, re.Pattern[str]] = {
    "index": re.compile(
        rf"^(?:index|indice)(?:[\s-]+[^\W\d_]{{1,15}}){{1,4}}\s*{_TRAILING}\s*$",
        re.IGNORECASE),
    "bibliography": re.compile(
        rf"^(?:bibliographie|bibliography|bibliografia)"
        rf"(?:[\s-]+[^\W\d_]{{1,15}}){{1,4}}\s*{_TRAILING}\s*$", re.IGNORECASE),
}


def _is_capitalised(text: str) -> bool:
    """True where the line is set in capitals — a printer's heading signal.

    Measured over cased letters only, so digits and punctuation neither help
    nor hurt, and a line without any letters is not a heading.
    """
    cased = [c for c in text if c.isalpha()]
    if len(cased) < 3:
        return False
    return sum(1 for c in cased if c.isupper()) / len(cased) >= 0.8


def region_of_heading(line: str) -> str | None:
    """The region a heading line opens, or None if it opens none.

    Returns None for anything that is not a plausible heading — prose, an
    empty line, a title too long to be one. Never guesses: a line that is not
    in the vocabulary is not a region, and §4.4 makes that the safe answer.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    folded = _fold(stripped)
    for region, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.match(folded):
                return region
    if _is_capitalised(stripped):
        for region, pat in _CAPITALISED.items():
            if pat.match(folded):
                return region
    return None


def _heading_candidates(page) -> list[str]:
    """The lines on a page that could carry a region heading.

    The confirmed outline title first — a heading the producer cut off the
    body still has to be seen — then the top of the page, where a region
    title stands. Deeper than that is body text.
    """
    lines = [ln.strip() for ln in page.body_lines if ln.strip()][:6]
    return ([page.heading.strip()] if page.heading else []) + lines


def _ubiquitous_heads(
    page_headers: list[str | None] | None,
    total: int,
    *,
    share: float = 0.4,
) -> set[str]:
    """Running heads that cover so much of the volume they distinguish nothing.

    A volume title printed on every verso says only that this is the volume.
    Read as evidence it does real damage: on a book set with alternating heads
    — volume title left, section title right — it closes the region on every
    other page, and the region flickers page by page (Bresson prints four
    indexes that way).

    This is Archilles' rule 1, learned there on EPUB filenames and true here
    too: a marker every unit carries is convention, not meaning. Check for
    contrast before believing a signal.
    """
    if not page_headers or total <= 0:
        return set()
    counts: Counter[str] = Counter(h for h in page_headers if h)
    return {head for head, n in counts.items() if n / total >= share}


def _opens_region(page) -> str | None:
    for line in _heading_candidates(page):
        name = region_of_heading(line)
        if name is not None:
            return name
    return None


def assign_regions(
    pages: list,
    *,
    page_headers: list[str | None] | None = None,
    prose_pages_to_close: int = 2,
    tail_fraction: float = 0.25,
) -> None:
    """Set ``page.region`` for every page, per §4.4.

    ``page_headers`` is the running head of each page, parallel to ``pages``
    (``reflow/running_elements.header_of_page``). Where one names a region it
    is the strongest evidence available and overrides the rules below: a
    heading is printed once, a running head repeats on every page of the
    region and is thereby self-confirming. A running head that names no region
    is no evidence either way — a volume that prints its title over the
    bibliography too must not thereby lose it.

    Front matter and the table of contents are named from the mode the
    reflow already assigned — those two the producer has always known. An
    apparatus region opens on a heading from the vocabulary and closes on the
    first of:

    - the next region heading,
    - a chapter heading the outline confirmed (a volume that starts a chapter
      is not in its bibliography any more),
    - ``prose_pages_to_close`` consecutive pages of running text.

    The last rule is why a stray *Abkürzungen:* inside an essay costs one page
    instead of a book. Two pages rather than one, because a densely set
    bibliography page can measure as prose on its own — and when the run does
    close a region, it closes it *from its first page*: the prose that proved
    the region over was never part of it.

    In the final ``tail_fraction`` of a volume the prose rule is suspended.
    It exists to keep a false positive from swallowing running text, and past
    that point there is almost none left to swallow: Bauer's twenty
    bibliography pages measure as prose throughout and would otherwise be
    named for one page only. The asymmetry of §4.4 is what licenses this —
    the risk it takes is a visible index, the risk it avoids is an invisible
    chapter.
    """
    from scriptor.reflow.core import estimate_body_width, is_prose_page

    width = estimate_body_width(pages)
    # A short list would silently pair headers with the wrong pages, so it is
    # refused rather than truncated.
    if page_headers is not None and len(page_headers) != len(pages):
        page_headers = None
    ubiquitous = _ubiquitous_heads(page_headers, len(pages))
    tail_begins = len(pages) * (1.0 - tail_fraction)
    current = "main"
    prose_run: list = []
    in_tail = False

    for position, page in enumerate(pages):
        mode = getattr(page, "mode", "main")
        if mode == "frontmatter":
            page.region = "front-matter"
            current, prose_run = "main", []
            continue
        if mode == "toc":
            page.region = "contents"
            current, prose_run = "main", []
            continue

        head = page_headers[position] if page_headers else None
        by_head = region_of_heading(head) if head else None
        # Frequency only devalues a head that names nothing. One that names a
        # region is evidence however often it occurs — a volume may well be
        # half bibliography, and its own title over those pages is the point.
        if by_head is None and head in ubiquitous:
            head = None
        if by_head is not None:
            page.region = by_head
            current, prose_run = by_head, []
            in_tail = False   # the head carries the region; no rule needs muting
            continue

        opened = _opens_region(page)
        if opened is not None:
            current, prose_run = opened, []
            # Remembered from where the region opened, not re-tested per page:
            # a region that began in the body keeps being closable even once
            # it has run into the tail.
            in_tail = position >= tail_begins
        elif current in _CLOSEABLE:
            # A confirmed chapter start ends the apparatus outright: the
            # outline is stronger evidence than the run of short lines that
            # kept the region open.
            if page.heading and region_of_heading(page.heading) is None:
                current, prose_run = "main", []
            elif head is not None and is_prose_page(page, width):
                # A running head that names something other than a region says
                # the page belongs to a named structure — an essay, a chapter —
                # and an apparatus is not one. This outranks the tail rule:
                # Anglo-Norman's APPENDIX sits 81% into a collective volume
                # with sixty-eight pages of further essays behind it, each
                # headed by its own title.
                current, prose_run = "main", []
            elif in_tail:
                prose_run = []
            elif is_prose_page(page, width):
                prose_run.append(page)
                if len(prose_run) >= prose_pages_to_close:
                    for earlier in prose_run:
                        earlier.region = "main"
                    current, prose_run = "main", []
            else:
                prose_run = []

        page.region = current


def marker(name: str) -> str:
    """The §4.4 block marker opening region ``name``."""
    return REGION_MARKER.format(name=name)


def render_metadata_block(chunking_strategy: str = "basic") -> str:
    """The YAML metadata block of §4.1, as its own block.

    Declaration only: it says which conventions the file follows and how a
    retrieval consumer should cut it. Nothing here is content, and a consumer
    that drops the block loses no word of the document.
    """
    return (
        "---\n"
        f"format_version: {FORMAT_VERSION}\n"
        f"chunking_strategy: {chunking_strategy}\n"
        "---"
    )


_METADATA_BLOCK = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)


def strip_metadata_block(text: str) -> str:
    """The document without its §4.1 metadata block.

    Part of the format, not a test helper: a consumer that wants the text and
    not the declaration should not have to know how the block is delimited.
    Text with no block is returned unchanged.
    """
    return _METADATA_BLOCK.sub("", text, count=1)
