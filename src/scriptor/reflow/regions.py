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

from scriptor.languages import NOT_ATTESTED, _NotAttested

# The version of PREPARED_FORMAT_SPEC this producer writes. Stated in the
# document itself (§4.1), because a prepared document outlives the release
# notes that describe it.
FORMAT_VERSION = "0.5.0"

# The marker of §4.4, on a line of its own.
REGION_MARKER = "[region: {name}]"

# The closed vocabulary of §4.4. Order is meaningless; membership is not.
REGION_NAMES = (
    "front-matter",
    "contents",
    "preface",
    "main",
    "bibliography",
    "index",
    "abbreviations",
    "notes",
    "appendix",
    "lists",
)

# Regions that name an apparatus — the ones a retrieval consumer wants to
# exclude. `appendix` is not among them (user decision, 2026-09-23): an
# appendix is as often a source as an aid — Gli Actus prints its edition of the
# text there, *De eerste minister* the instruction it discusses — and §4.4
# would rather show an appendix than lose one.
APPARATUS = ("bibliography", "index", "abbreviations", "notes", "lists")

# Regions the closing rules apply to. A table of contents is not apparatus,
# but it must close like one: a volume that prints its contents at the end
# (Pückert 1899, Guilhiermoz 1902) would otherwise carry `contents` over every
# chapter that follows, which is the same silent loss by another name. An
# appendix closes for the same reason, apparatus or not.
_CLOSEABLE = APPARATUS + ("appendix", "contents")

# Heading vocabulary, grouped by the language each word belongs to. Matched
# against a whole heading line, case- and accent-insensitively (an OCR layer
# drops diacritics often enough that requiring them would cost more than it
# protects).
#
# The languages are catalogued in ``scriptor.languages``; a word that belongs
# to several is listed under each of them, and ``tests/test_languages.py``
# holds every language answerable for every region. Adding a language is
# adding entries here — the matching rule below stays untouched. CJK is out:
# these patterns key on word boundaries, which do not carry there.
#
# The order of the *regions* carries meaning and must not change: matching
# returns the first region that fits, which is how a bare "Indice" resolves to
# `contents` rather than `index`. The order of languages within a region does
# not, since matching only asks whether some pattern of the region fits.
_VOCABULARY: dict[str, dict[str, tuple[str, ...] | _NotAttested]] = {
    "bibliography": {
        # "Quellen- und Literaturverzeichnis" too, hence the optional lead,
        # and "Sekundärliteratur" / "Primärliteratur", which grow onto the
        # word rather than standing in front of it.
        "de": (
            r"(?:quellen[-\s–]*und[-\s]*)?(?:sekund[äa]r|prim[äa]r|forschungs)?"
            r"literatur(?:verzeichnis|nachweis)?",
            # Editions of the sources, the usual heading for a source
            # bibliography in classical scholarship (Themistios: "VII
            # Editionen und Übersetzungen").
            r"editionen(?: und [üu]bersetzungen)?", r"textausgaben",
            r"(?:quellen|siglen)?(?:verzeichnis)?[-\s]*bibliographie",
            r"bibliographie", r"bibliografie",
            r"quellenverzeichnis", r"quellen und literatur",
            r"verzeichnis der (?:zitierten |verwendeten )?literatur",
        ),
        "en": (
            r"(?:select(?:ed)?\s+|primary\s+|secondary\s+|general\s+)?bibliography",
            r"works cited", r"list of works", r"references",
            r"(?:list of |primary |printed )?sources",
        ),
        "fr": (
            r"bibliographie(?: s[ée]lective| g[ée]n[ée]rale)?",
            r"r[ée]f[ée]rences(?: bibliographiques)?",
            r"sources(?: et bibliographie)?",
        ),
        "it": (
            r"bibliografia",
            r"fonti(?: e bibliografia)?", r"riferimenti bibliografici",
        ),
        "es": (r"bibliograf[íi]a", r"obras citadas"),
        "pt": (
            r"bibliografia", r"refer[êe]ncias(?: bibliogr[áa]ficas)?",
            r"fontes(?: e bibliografia| impressas| manuscritas)?",
        ),
        "nl": (
            r"bibliografie", r"literatuur(?:lijst|opgave)?",
            r"geraadpleegde werken",
        ),
        "la": (r"bibliographia", r"conspectus librorum"),
        "ru": (
            r"библиография", r"список литературы", r"литература",
            r"источники(?: и литература)?",
        ),
    },
    # Lists a reader looks things up in: glossaries, lists of illustrations,
    # maps and tables, lists of contributors, credits. Every word below is
    # attested in the library's EPUB contents or the corpus (G7, 2026-09-23).
    # Before `index`, because Spanish heads a list of figures "Índice de
    # figuras", which the index pattern `índice de …` would take. A chronology
    # is left out on purpose: it is as often an argument set as a table.
    # The bare plurals ("Figures", "Maps", "Karten") are in
    # _TITLED_VOCABULARY: alone on a line they may be the last word of a
    # sentence.
    "lists": {
        "de": (
            r"(?:kleines )?glossar", r"abbildungs(?:verzeichnis|nachweis)",
            r"(?:karten|tabellen|tafel)verzeichnis",
            r"verzeichnis der (?:karten|abbildungen|tabellen|tafeln|pl[äa]ne)"
            r"(?: und \w+)?",
            r"autorenverzeichnis", r"autorinnen und autoren",
            r"(?:[üu]ber die|zu den) autoren", r"autoreninfo",
        ),
        "en": (
            r"glossary", r"list of (?:illustrations|figures|maps|plates|tables|"
            r"contributors)(?:,? and (?:[^\W\d_]+ )?[^\W\d_]+)?",
            r"table of illustrations",
            r"(?:about |notes on )?(?:the )?contributors(?: and editors)?",
            r"(?:about the )?editors? and contributors",
            r"illustration credits", r"(?:sources|credits) (?:for|of) illustrations",
            r"notes? on (?:the )?(?:illustrations|transliteration)",
        ),
        "fr": (
            r"glossaire",
            r"table (?:des|et cr[ée]dits des) (?:illustrations|figures|cartes)"
            r"(?: et des tableaux)?",
            r"l[ée]gendes des figures", r"les auteurs",
        ),
        "it": (
            r"glossario", r"indice delle (?:illustrazioni|tavole|figure)",
            r"elenco delle (?:illustrazioni|tavole|figure)", r"gli autori",
        ),
        "es": (
            r"glosario", r"[íi]ndice de (?:figuras|ilustraciones|mapas|l[áa]minas)",
        ),
        "pt": NOT_ATTESTED,
        "nl": NOT_ATTESTED,
        "la": NOT_ATTESTED,
        "ru": NOT_ATTESTED,
    },
    "index": {
        # Personen-, Sach-, Orts-, Namen-, Stellen-, Autoren-, Bibelstellen-
        "de": (
            r"(?:\w+[-\s]?)?register",
            r"(?:namen|orts|personen|sach|stellen)verzeichnis",
            r"index(?: der \w+)?",
        ),
        "en": (
            r"(?:general |subject |name |author |place |scriptural )?index(?:es)?",
            r"indices", r"index of (?:names|subjects|places|persons|passages)",
        ),
        # "Index des textes cités", "Index des auteurs modernes"; the
        # complement runs to several words, as it does in Spanish below.
        "fr": (
            r"index des(?:[\s-]+[^\W\d_]{1,15}){1,4}",
            r"index(?: g[ée]n[ée]ral| nominum)?", r"table onomastique",
        ),
        # The complement is what makes it a register. Bare "Indice"/"Índice"
        # is the table of contents in Italian, Spanish and Portuguese and is
        # listed under `contents`; only English, German, French and Latin use
        # the plain word for the back-of-book index.
        "it": (
            r"indice(?: dei nomi| dei luoghi| analitico| onomastico| dei manoscritti)",
        ),
        "es": (
            r"[íi]ndice de(?:[\s-]+[^\W\d_]{1,15}){1,4}",
            r"[íi]ndice(?: onom[áa]stico| anal[íi]tico| tem[áa]tico)",
        ),
        # "Índice de Nomes e Pseudônimos" — the complement runs to several
        # words, so it is bounded by count rather than listed exhaustively.
        "pt": (
            r"[íi]ndice de(?:[\s-]+[^\W\d_]{1,15}){1,4}",
            r"[íi]ndice(?: onom[áa]stico| anal[íi]tico| tem[áa]tico| remissivo)",
        ),
        "nl": (r"register(?: van \w+)?", r"zaakregister", r"namenregister"),
        "la": (
            r"index (?:nominum|rerum|locorum|verborum|auctorum|codicum|"
            r"manuscriptorum|fontium)",
        ),
        "ru": (
            r"указатель(?: имён| имен| названий)?", r"именной указатель",
            r"предметный указатель",
        ),
    },
    "abbreviations": {
        "de": (
            r"abk[üu]rzungs(?:verzeichnis|liste)?", r"abk[üu]rzungen",
            r"siglen(?:verzeichnis)?", r"verzeichnis der abk[üu]rzungen",
        ),
        "en": (
            r"(?:list of |table of )?abbreviations", r"sigla", r"short titles",
        ),
        "fr": (
            r"abr[ée]viations(?: et sigles)?", r"liste des abr[ée]viations",
            r"sigles",
        ),
        "it": (r"abbreviazioni",),
        "es": (
            r"siglas(?: e abreviaturas)?",
            r"abreviaturas?(?:[\s-]+(?:do|da|de|e)[\s-]+[^\W\d_]{1,15}){0,2}",
        ),
        "pt": (
            r"siglas(?: e abreviaturas)?",
            r"abreviaturas?(?:[\s-]+(?:do|da|de|e)[\s-]+[^\W\d_]{1,15}){0,2}",
        ),
        "nl": (r"afkortingen(?:lijst)?", r"lijst van afkortingen"),
        "la": (r"index siglorum", r"sigla"),
        "ru": (r"список сокращений", r"сокращения", r"условные обозначения"),
    },
    "contents": {
        # A table of contents at the *end* of a volume — Guilhiermoz 1902 and
        # Pückert 1899 both put it there. assign_modes only reaches the ones it
        # meets while still in front matter, so the region needs its own words.
        "de": (r"inhalts(?:verzeichnis|[üu]bersicht|angabe)?", r"inhalt"),
        "en": (r"(?:table of )?contents",),
        "fr": (r"table des mati[èe]res", r"sommaire"),
        # `sommario` is the counterpart to `sommaire`, and the word that made
        # the case for one vocabulary instead of two: it lived only in the
        # mode triggers, which knew no Dutch, while this table knew no
        # `sommario`. Bare "Indice"/"Índice" — see the note under `index`.
        "it": (r"sommario", r"[íi]ndice(?: generale)?"),
        "es": (r"[íi]ndice(?: general)?",),
        "pt": (r"[íi]ndice(?: geral)?", r"sum[áa]rio"),
        "nl": (r"inhoud(?:sopgave)?",),
        "ru": (r"оглавление", r"содержание"),
        # No Latin volume in the corpus prints a table of contents: the word
        # is used for indices (see `index`), not for the front matter.
        "la": NOT_ATTESTED,
    },
    "preface": {
        # What a book says about itself before it begins: how it came about,
        # and who is thanked. Named, never excluded — see APPARATUS. Ten of
        # sixteen measured volumes carry one, which is why this name and not
        # the six other candidates measured beside it.
        "de": (
            r"vorwort(?: und dank(?:sagung)?)?", r"geleitwort", r"zum geleit",
            r"danksagung(?:en)?", r"vorbemerkung(?:en)?",
        ),
        "en": (r"preface", r"acknowledge?ments?", r"author's note"),
        "fr": (r"pr[ée]face", r"avant[- ]propos", r"remerciements"),
        "it": (r"prefazione", r"premessa", r"ringraziamenti"),
        "es": (
            r"prefacio", r"agradecimientos", r"nota (?:previa|del autor)",
        ),
        "pt": (r"pref[áa]cio", r"agradecimentos"),
        "nl": (r"voorwoord", r"dankwoord", r"woord vooraf"),
        "ru": (r"предисловие", r"благодарности"),
        # A Latin preface is titled "praefatio" — but no volume in the corpus
        # prints one, and one attestation would be needed before guessing.
        "la": NOT_ATTESTED,
    },
    "notes": {
        # A collected notes section, as distinct from the footnotes of §4.3.
        "de": (r"anmerkungen", r"endnoten", r"anmerkungsapparat"),
        # Plural only. A volume that heads a page "NOTE" is nearly always
        # making a publisher's remark, not opening an apparatus — Baynes does
        # exactly that on its imprint page.
        "en": (r"notes", r"endnotes", r"reference notes"),
        "fr": (r"notes",),
        # Italian would head such a section "Note" — singular in form, and
        # excluded for the reason given above. Nothing else is attested.
        "it": NOT_ATTESTED,
        "es": (r"notas",),
        "pt": (r"notas",),
        "nl": (r"noten",),
        "la": (r"adnotationes",),
        "ru": (r"примечания", r"комментарии"),
    },
    "appendix": {
        # A numbered or lettered appendix names itself that way — "Appendix
        # IV", "Apéndice I", "ANEXO 2" — so the ordinal may follow the word as
        # well as precede it. A single trailing letter counts as an ordinal
        # too ("Anexo A"), but only a single one: two letters are a word, and
        # a word after the noun makes it a sentence rather than a heading.
        "de": (r"anh[äa]nge?", r"anlagen?", r"beilagen?", r"tabellenanhang"),
        "en": (
            r"appendix(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]))?", r"appendices",
        ),
        # The singular "appendice" is French and Italian alike, and lives in
        # _TITLED_VOCABULARY: alone on a line it is as often the last word of
        # a wrapped sentence ("… nell'" / "appendice.") as a heading. The
        # entries here once read `appendici?`, which never met the singular.
        "fr": (r"annexes?",),
        "it": (r"appendici(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]\b))?",),
        "es": (
            r"ap[ée]ndices?(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]\b))?",
            r"anexos?(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]\b))?",
        ),
        "pt": (
            r"ap[êe]ndices?(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]\b))?",
            r"anexos?(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]\b))?",
        ),
        "nl": (r"bijlagen?",),
        "ru": (r"приложения?",),
        # "Appendix" is Latin, but a volume that prints it is setting an
        # English or German heading; no Latin-language attestation.
        "la": NOT_ATTESTED,
    },
}

# An optional ordinal in front of the title: "13.", "IV.", "A.", "§ 3" — and
# compounded, "VIII.1", "3.2.1". One level was not enough: De Gruyter heads
# "VIII.1 Abkürzungen" and "VIII.2 Literatur", so a heading whose bare word the
# vocabulary knows fell through on its number alone. It cannot make a heading
# out of prose, because what follows still has to match a whole entry.
_PREFIX = r"(?:(?:§\s*)?(?:\d{1,3}|[ivxlcdm]{1,6}|[a-z])(?:\.\d{1,3})*[.)]?\s+)?"

# A heading is short. Beyond this the line is prose that happens to open with
# the word, and prose is never a region marker.
_MAX_HEADING_CHARS = 48

# A full stop with a letter on either side. Between two letters it is not
# punctuation but a scanning artefact: Lizzi Testa's running head arrives as
# "Bibliogra.fia", and thirty-five pages of bibliography hang on reading it
# anyway. A stop at a word boundary is left alone — there it may be an
# abbreviation, and dropping it would join two words into one.
_INNER_STOP = re.compile(r"(?<=[^\W\d_])\.(?=[^\W\d_])")


def _undiacritic(text: str) -> str:
    """Drop combining marks, so 'Índice' and 'indice' become the same word.

    Applied to the patterns as well as to the line, or the two would disagree
    exactly where it matters: NFD decomposes Russian 'ё' into 'е' plus a
    combining mark, so a pattern written 'имён' would never meet a folded
    'имен'.

    Case is deliberately left alone here. The patterns are compiled with
    IGNORECASE, and lowercasing a *pattern* silently inverts its character
    classes — ``[^\\W\\d_]`` means "a letter", ``[^\\w\\d_]`` means the exact
    opposite.
    """
    decomposed = unicodedata.normalize("NFD", text.strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _fold(text: str) -> str:
    """A heading line, normalised for matching.

    No diacritics, no case, no full stop dropped inside a word by the scanner,
    and no invisible characters: extraction leaves control and format codes in
    the text — Asclepios carries a backspace after "Literatuur" — and nothing
    in a printed heading is invisible, so they cannot be part of one.

    Runs of whitespace collapse to one. Letter-spaced and justified headings
    arrive with doubled spaces ("Index  des  textes cités"), and normalising
    here spares every pattern from having to spell `\\s+` between its words.
    """
    visible = "".join(
        c for c in _undiacritic(text) if unicodedata.category(c) not in ("Cc", "Cf")
    )
    return _INNER_STOP.sub("", " ".join(visible.lower().split()))


# What may trail a heading: a closing stop or colon, because older typography
# sets headings that way ("Inhaltsübersicht.", Pückert 1899) — and the marks a
# scan turns those into. Guilhiermoz's running head arrives as "INDEX
# ALPHABÉTIQUE ·", its printed full stop read back as a middle dot; refusing
# it costs nine pages of index. Tolerating the tail costs nothing, because
# what precedes it still has to be a whole vocabulary word: no sentence
# becomes a heading by ending in a period.
_TRAILING = r"[.,:;·•∙]?"

def _patterns_of(by_language: dict[str, tuple[str, ...] | _NotAttested]) -> list[str]:
    """Every pattern of a region, the language grouping read away again.

    Language order is immaterial here: matching asks only whether *some*
    pattern of the region fits, never which language answered.
    """
    out: list[str] = []
    for patterns in by_language.values():
        if patterns is NOT_ATTESTED:
            continue
        out.extend(patterns)
    return out


_COMPILED: dict[str, tuple[re.Pattern[str], ...]] = {
    region: tuple(
        re.compile(_undiacritic(rf"^{_PREFIX}{alt}\s*{_TRAILING}\s*$"), re.IGNORECASE)
        for alt in _patterns_of(by_language)
    )
    for region, by_language in _VOCABULARY.items()
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


# Headings the whole-line vocabulary cannot take, because the region word
# carries a qualifier or a complement: "Index of Modern Authors", "Scripture
# Index", "Notes to the Translation", "Appendix C. Dream Transcripts …". An
# EPUB contents names its apparatus this way far more often than a running head
# does (G7, 2026-09-23: 1 350 chunks of apparatus the plain words missed).
#
# Each entry is a closed list of complements, never "the word and anything
# after it": "Notes on a nameless philosophy" and "Literatur und
# Mehrsprachigkeit" are chapters. And every entry is tried only on a line set
# as a heading (``_is_titled``), which is what keeps "Appendix 5. The most
# substantive contradiction that may exist …" — a line of prose — out.
#
# Completeness per language is owed by _VOCABULARY alone; a language missing
# here has simply not shown the form.
_DESIGNATOR = (r"(?:[ivxlcdm]{1,5}|\d{1,2}|[a-z]|one|two|three|four|five|six|"
               r"seven|eight|nine|ten)\b")

# An appendix titled after its designator: word, optional number or letter,
# separator, title. Only this form may run past _MAX_HEADING_CHARS, and only
# with the designator (see _DESIGNATED_APPENDIX).
def _appendix(word: str) -> str:
    return rf"{word}(?:\s*{_DESIGNATOR})?\s*[.:—–]\s*[^\W_].*"


# A word that qualifies the region word — "Scripture Index", "Consolidated
# Bibliography" — but never an article or a pronoun: "Der Index" opens a
# sentence, not a register.
_QUALIFIER = (r"(?!(?:the|this|that|these|our|his|her|its|their|each|every|any|"
              r"der|die|das|den|dem|des|ein|eine|einen|le|la|les|il|lo|el|los|las|"
              r"het|een)\s)[^\W\d_]{3,15}")


_TITLED_VOCABULARY: dict[str, dict[str, tuple[str, ...]]] = {
    "bibliography": {
        "en": (
            # Consolidated / Supplementary / Annotated Bibliography
            rf"(?:{_QUALIFIER}\s+){{1,2}}bibliography",
            r"bibliography\s+(?:and|for|of|in)\s+.{2,60}",
            r"(?:sources|references)\s+and\s+bibliography",
        ),
    },
    "index": {
        "en": (
            r"(?:index|indices|indexes)\s+(?:of|to|by)\s+.{2,70}",
            # Scripture Index, Ancient Sources Index, Key Sites Index
            rf"(?:{_QUALIFIER}\s+(?:and\s+)?){{1,3}}index(?:es)?",
        ),
    },
    "notes": {
        "en": (
            r"footnotes",
            r"notes\s+(?:and references|\d{1,2}|to (?:the )?"
            r"(?:chapters?|translation|text|introduction|part)\b.*)",
            # Notes on the text are notes. Notes on contributors, illustrations
            # or transliteration are lists of another kind and stay unnamed
            # until the vocabulary has a name for them.
            r"notes on (?:the )?(?:text|translation|sources|editions)\b.*",
            r"(?:bibliographical|biographical|translator['’]?s|editor['’]?s|"
            r"explanatory|textual|critical|additional|supplementary|general)\s+notes",
        ),
        "de": (
            r"fu(?:ß|ss)noten",
            r"anmerkungen zu(?:m| den)? (?:kapitel|text)\b.*",
        ),
        "fr": (r"notes\s+(?:compl[ée]?mentaires|additionnelles)",),
    },
    "lists": {
        "en": (
            r"(?:colou?r |line )?(?:illustrations|figures|maps|plates|tables)"
            r"(?:,? and (?:figures|tables|maps|plates))?",
            r"glossary of .{2,60}",
        ),
        "de": (r"karten", r"abbildungen"),
        "fr": (r"cartes",),
        "it": (r"illustrazioni",),
        "es": (r"ilustraciones",),
    },
    "appendix": {
        "en": (_appendix(r"(?:appendix|appendices)"),),
        "de": (_appendix(r"(?:anhang|anh[äa]nge|anlagen?|beilagen?)"),),
        "fr": (r"appendice(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]))?",
               _appendix(r"(?:annexes?|appendices?)")),
        "it": (r"appendice(?:\s+(?:[ivxlcdm]+|\d{1,2}|[a-z]))?",
               _appendix(r"(?:appendic[ei])")),
        "es": (_appendix(r"(?:ap[ée]ndices?|anexos?)"),),
        "pt": (_appendix(r"(?:ap[êe]ndices?|anexos?)"),),
        "nl": (_appendix(r"(?:bijlagen?)"),),
    },
}

_TITLED_COMPILED: dict[str, tuple[re.Pattern[str], ...]] = {
    region: tuple(
        re.compile(_undiacritic(rf"^{_PREFIX}{alt}\s*{_TRAILING}\s*$"), re.IGNORECASE)
        for alt in _patterns_of(by_language)
    )
    for region, by_language in _TITLED_VOCABULARY.items()
}

# An appendix that states its number or letter may carry a title of any
# ordinary length; without one, a long line is more likely a bibliography
# entry that opens with the word ("Anhang : Neu gefundene Philonfragmente,
# dans les Sitzungsberichte").
_DESIGNATED_APPENDIX = re.compile(
    _undiacritic(
        rf"^{_PREFIX}(?:appendix|appendices|anhang|anh[äa]nge|anlagen?|beilagen?|"
        rf"annexes?|appendic[ei]s?|ap[ée]ndices?|ap[êe]ndices?|anexos?|bijlagen?)"
        rf"\s*{_DESIGNATOR}\s*[.:—–]"),
    re.IGNORECASE)

_MAX_TITLED_CHARS = 100

# Ornament a volume sets around a heading: "· INDEX ·", "[Anmerkungen]".
_ORNAMENT = re.compile(r"^[\[(·•∙*\s]+|[\])·•∙*\s]+$")


def _is_titled(text: str) -> bool:
    """True where the line is set as a heading: title case or capitals.

    At least half the words of four letters or more open with a capital.
    Half, not all, because sentence-case headings with proper nouns exist
    ("Bijlage 2: categorieën pamfletten uit de Tweede Engelse Oorlog"); a line
    of prose that happens to open with a region word reaches one in eight.
    """
    words = [w for w in re.findall(r"[^\W\d_]+", text) if len(w) >= 4]
    if not words:
        words = re.findall(r"[^\W\d_]+", text)
    if not words:
        return False
    return sum(1 for w in words if w[0].isupper()) * 2 >= len(words)


def _region_of_whole_line(stripped: str) -> str | None:
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


def _region_of_titled(bare: str) -> str | None:
    if not bare or len(bare) > _MAX_TITLED_CHARS or not _is_titled(bare):
        return None
    folded = _fold(bare)
    if len(bare) > _MAX_HEADING_CHARS and not _DESIGNATED_APPENDIX.match(folded):
        return None
    for region, patterns in _TITLED_COMPILED.items():
        for pat in patterns:
            if pat.match(folded):
                return region
    return None


def region_of_heading(line: str) -> str | None:
    """The region a heading line opens, or None if it opens none.

    Returns None for anything that is not a plausible heading — prose, an
    empty line, a title too long to be one. Never guesses: a line that is not
    in the vocabulary is not a region, and §4.4 makes that the safe answer.

    Three tries, each narrower in what it forgives: the line as it stands,
    the line without ornament around it, and — only where it is set as a
    heading — the region word with a qualifier or complement.
    """
    stripped = line.strip()
    region = _region_of_whole_line(stripped)
    if region is not None:
        return region
    bare = _ORNAMENT.sub("", " ".join(stripped.split()))
    if bare != stripped:
        region = _region_of_whole_line(bare)
        if region is not None:
            return region
    return _region_of_titled(bare)


# Where a running head stops naming its section and starts describing it.
_HEAD_SEPARATOR = re.compile(r"\s*[.:;—–|/]\s+|\s+[—–|/]\s*")


def region_of_running_head(head: str) -> str | None:
    """The region a running head names, or None.

    Like ``region_of_heading``, but a head is also tried up to its first
    separator. Volumes head every page of a section with its title *and*
    subtitle — "ANEXO 1. ACCIONES VIOLENTAS" — and read whole that is in no
    vocabulary, so it counted as a foreign head and closed the very region it
    names. Cutting at the separator is safe in the other direction: a volume
    title cut the same way ("Eduardo Callaey / La masonería") still names
    nothing.
    """
    whole = region_of_heading(head)
    if whole is not None:
        return whole
    first = _HEAD_SEPARATOR.split(head.strip(), maxsplit=1)[0]
    if first and first != head.strip():
        return region_of_heading(first)
    return None


def _heading_candidates(page) -> list[str]:
    """The lines on a page that could carry a region heading.

    The confirmed outline title first — a heading the producer cut off the
    body still has to be seen — then the top of the page, where a region
    title stands. Deeper than that is body text.

    Adjacent lines are also offered joined, and offered *first*, because a
    heading may be broken across two of them: Callaey sets ÍNDICE / ONOMÁSTICO
    that way, and read line by line the first half says "contents" — right for
    the bare word, wrong for this page, and sixteen pages of register go under
    the wrong name. The joined reading is the more specific one wherever both
    match, so trying it first resolves the pair correctly. It cannot invent a
    region: the join still has to match a whole vocabulary entry.
    """
    lines = [ln.strip() for ln in page.body_lines if ln.strip()][:6]
    pairs = [f"{a} {b}" for a, b in zip(lines, lines[1:])]
    return ([page.heading.strip()] if page.heading else []) + pairs + lines


def _ubiquitous_heads(
    page_headers: list[str | None] | None,
    total: int,
    *,
    span: float = 0.4,
) -> set[str]:
    """Running heads that reach so far across the volume they distinguish nothing.

    A volume title printed on every verso says only that this is the volume.
    Read as evidence it does real damage: on a book set with alternating heads
    — volume title left, section title right — it closes the region on every
    other page, and the region flickers page by page (Bresson prints four
    indexes that way, Callaey five appendices).

    Measured by *reach*, not by count. Callaey's verso head lands on about a
    third of the pages, because chapter openings carry none, and any threshold
    on frequency lets it through — but it runs from the first chapter to the
    last page of the index, and that is what gives it away. A section title
    clusters where its section is.

    This is Archilles' rule 1, learned there on EPUB filenames and true here
    too: a marker every unit carries is convention, not meaning. Check for
    contrast before believing a signal.
    """
    if not page_headers or total <= 0:
        return set()
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for position, head in enumerate(page_headers):
        if not head:
            continue
        first.setdefault(head, position)
        last[head] = position
    return {
        head
        for head in first
        if (last[head] - first[head] + 1) / total >= span
    }


def _opens_region(page) -> str | None:
    for line in _heading_candidates(page):
        name = region_of_heading(line)
        if name is not None:
            return name
    return None


def _is_roman_label(label: str) -> bool:
    from scriptor.reflow.pagelabel import MIN_ROMAN_LEN, ROMAN_RE

    s = label.strip().lower()
    return len(s) >= MIN_ROMAN_LEN and bool(ROMAN_RE.match(s))


def front_matter_zone_end(
    pages: list,
    *,
    page_headers: list[str | None] | None = None,
    max_fraction: float = 0.1,
) -> int:
    """Index of the first body page — where the front matter stops.

    Two signals, in order of how much they can be trusted.

    The **pagination** is the publisher's own statement and needs no
    vocabulary: a volume that sets its front matter in roman numerals and
    restarts at 1 has said where its body begins (Themistios: contents
    XI–XIII, body from 1).

    Where a volume paginates straight through (Bauer: preface on 7), the
    fallback is the **last list printed in the opening tenth** — a table of
    contents or a list of abbreviations. The bound matters more than it looks:
    nine of sixteen measured volumes print their contents at the *end*, and
    without it one at 98 % would declare the whole book front matter.

    That fallback has to read the running heads, not only the mode. Bauer's
    table of contents is not ``mode=toc`` on a single page: it is recognised
    entirely from the head "Inhaltsverzeichnis" that all eight pages carry.
    Reading the mode alone closed the zone after the five title pages, one
    position ahead of the preface — which then counted as body text.

    A preface **adjoining** the zone extends it, and only then. Reading the
    lists alone put the boundary on the last one, so a volume that prints its
    contents first and its preface behind it (Lizzi Testa) ended its front
    matter on the very page the preface opens, and no such preface could ever
    be named. Requiring the page to adjoin what has been found so far is what
    keeps the rule from arguing in a circle: a stray "Vorwort zur Neuausgabe"
    behind a few pages of running text would otherwise extend the zone to
    itself, and licence itself by doing so.

    Returns 0 where neither signal fires, which reads as "no front matter" and
    leaves every page to the ordinary rules.
    """
    if page_headers is not None and len(page_headers) != len(pages):
        page_headers = None

    seen_roman = False
    for position, page in enumerate(pages):
        label = (getattr(page, "label", None) or "").strip()
        if not label:
            continue
        if _is_roman_label(label):
            seen_roman = True
        elif seen_roman and label.isdigit():
            return position

    limit = max(1, int(len(pages) * max_fraction))
    end = 0
    for position, page in enumerate(pages[:limit]):
        if getattr(page, "mode", "main") in ("frontmatter", "toc"):
            end = position + 1
            continue
        head = page_headers[position] if page_headers else None
        names = {_opens_region(page), region_of_running_head(head) if head else None}
        if names & {"contents", "abbreviations"}:
            end = position + 1
        elif "preface" in names and position == end:
            end = position + 1
    return end


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
    zone_end = front_matter_zone_end(pages, page_headers=page_headers)
    current = "main"
    prose_run: list = []
    in_tail = False

    def names_region(at: int) -> str | None:
        if not page_headers or not 0 <= at < len(page_headers) or not page_headers[at]:
            return None
        return region_of_running_head(page_headers[at])

    for position, page in enumerate(pages):
        mode = getattr(page, "mode", "main")
        head = page_headers[position] if page_headers else None
        by_head = region_of_running_head(head) if head else None
        # Frequency only devalues a head that names nothing. One that names a
        # region is evidence however often it occurs — a volume may well be
        # half bibliography, and its own title over those pages is the point.
        if by_head is None and head in ubiquitous:
            head = None
        if by_head is not None:
            page.region = by_head
            current, prose_run = by_head, []
            # Same test as for a region opened by a heading: whether the tail
            # rule applies is a question about where in the volume this page
            # sits, not about which signal named it. Pouderon's bibliography
            # opens on a head and then loses it to the volume title — with the
            # rule switched off here, the prose rule closed it after one page
            # of twelve.
            in_tail = position >= tail_begins
            continue

        opened = _opens_region(page)
        # A preface is named only where it stands in the opening zone. Behind
        # it the same word means a chapter that leads into the argument —
        # Pouderon prints "Introduction" twice, six pages of it in front and a
        # whole PREMIÈRE PARTIE of four chapters after — and §4.4 would rather
        # carry a stray page of thanks than lose one of those.
        if opened == "preface" and position >= zone_end:
            opened = None

        # The mode is a fallback, not an override, and the coarsest evidence
        # there is. It answers per page from a trigger that fires once and
        # then persists: a bare "Índice" opening an index sets `toc` for every
        # page after it, and Callaey's index alternates recto/verso, so the
        # region flickered index/contents page by page. So the mode may name a
        # page that has no region of its own — it may not overrule a region
        # already running, nor a page that names itself.
        #
        # `preface` joins `main` here, and only those two. A preface runs a
        # page or three and the contents follows it directly; if the fallback
        # kept waiting for `main`, the contents behind a preface would never
        # be named. An apparatus already running still may not be overruled —
        # that is the defect this condition was written for.
        if (opened is None and current in ("main", "preface")
                and mode in ("frontmatter", "toc")):
            page.region = "front-matter" if mode == "frontmatter" else "contents"
            current, prose_run = "main", []
            continue

        if opened is not None:
            current, prose_run = opened, []
            # Remembered from where the region opened, not re-tested per page:
            # a region that began in the body keeps being closable even once
            # it has run into the tail.
            in_tail = position >= tail_begins
        elif current == "preface" and position >= zone_end:
            # A preface ends where the front matter does. None of the closing
            # rules below reach it — they are written for an apparatus, and the
            # prose rule would end a preface on its second page, a preface
            # being prose. Left unclosed it ran to the next region of any kind:
            # on Lizzi Testa that was the bibliography, 438 pages later. The
            # zone is the same evidence that opened it, so the region lasts
            # exactly as long as the grounds for naming it.
            current, prose_run = "main", []
        elif current == "contents" and mode == "main":
            # The reflow's own frontmatter->main transition ends a table of
            # contents exactly: it fires on the first page that reads as
            # running text. Waiting for the prose rule instead would let the
            # contents region reach two pages into the first chapter.
            current, prose_run = "main", []
        elif current in _CLOSEABLE:
            # A confirmed chapter start ends the apparatus outright: the
            # outline is stronger evidence than the run of short lines that
            # kept the region open.
            if page.heading and region_of_heading(page.heading) is None:
                current, prose_run = "main", []
            elif (head is not None and is_prose_page(page, width)
                  and not (names_region(position - 1) == current
                           and names_region(position + 1) is not None)):
                # A running head that names something other than a region says
                # the page belongs to a named structure — an essay, a chapter —
                # and an apparatus is not one. This outranks the tail rule:
                # Anglo-Norman's APPENDIX sits 81% into a collective volume
                # with sixty-eight pages of further essays behind it, each
                # headed by its own title.
                #
                # Unless the head is enclosed: the page before it is headed
                # with this region's name and the page after it with a region.
                # That is a section set with its name on one side and its title
                # on the other — Gli Actus: APPENDICE verso, "LA DISPUTA FRA
                # SILVESTRO E GIUDEI: IL TESTO" recto — and read as foreign,
                # the title closed the appendix on every recto.
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


def render_metadata_block(chunking_strategy: str = "basic",
                          pagination: str | None = None,
                          structure: str | None = None) -> str:
    """The YAML metadata block of §4.1, as its own block.

    Declaration only: it says which conventions the file follows and how a
    retrieval consumer should cut it. Nothing here is content, and a consumer
    that drops the block loses no word of the document.

    ``pagination`` states how far the page markers of this document can be
    trusted -- which edge the volume paginates at, and how much of it stated its
    own numbers rather than being counted. A consumer weighing a citation needs
    that and cannot derive it from the markers, since a computed label looks
    exactly like a printed one. Omitted where no verdict was taken, so a caller
    that only wants the text is unaffected.

    ``structure`` says in one line how deep this volume divides and on which
    level it opens its chapters (§6.5). Like the pagination line it is a
    summary, not the data: the structure sidecar carries that, and a reader
    who only wants to know whether the tree is worth asking for reads here.
    """
    lines = [
        "---",
        f"format_version: {FORMAT_VERSION}",
        f"chunking_strategy: {chunking_strategy}",
    ]
    if pagination is not None:
        lines.append(f"pagination: {pagination}")
    if structure is not None:
        lines.append(f"structure: {structure}")
    lines.append("---")
    return "\n".join(lines)


_METADATA_BLOCK = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)


def strip_metadata_block(text: str) -> str:
    """The document without its §4.1 metadata block.

    Part of the format, not a test helper: a consumer that wants the text and
    not the declaration should not have to know how the block is delimited.
    Text with no block is returned unchanged.
    """
    return _METADATA_BLOCK.sub("", text, count=1)


def read_metadata_block(text: str) -> dict[str, str] | None:
    """The fields of the §4.1 metadata block, or None where the text opens without one.

    The block is flat ``key: value`` lines, as ``render_metadata_block`` writes
    them, and that is all this reads -- not YAML at large. Values stay strings; a
    value a person put in quotes reads as its text. Fields nobody here knows are
    kept, because the spec tells a consumer to ignore them, not this reader.
    """
    m = _METADATA_BLOCK.match(text)
    if m is None:
        return None
    fields: dict[str, str] = {}
    for line in m.group(0).splitlines()[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields
