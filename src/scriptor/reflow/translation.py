"""Translation profile (stage 2c): master Markdown -> translation-ready MD.

Pure string post-processor (no I/O). Protects elements that must not be
translated with <dnt>…</dnt> tags and removes open confidence flags
(strip-and-pass). See
docs/superpowers/specs/2026-06-21-uebersetzungs-profil-design.md.
"""

from __future__ import annotations

import re
from collections.abc import Callable

DNT_OPEN = "<dnt>"
DNT_CLOSE = "</dnt>"

# http(s):// or www.… up to whitespace/'<'. Trailing punctuation is split off
# during wrapping (see protect_urls), not here.
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<]+", re.IGNORECASE)

# Title quote pairs: German „…“, straight "…", guillemets »…« (turned round
# to «…» where a line opens with «, see protect_quoted).
QUOTE_PAIRS = [("„", "“"), ('"', '"'), ("»", "«")]

# Pandoc footnote definition line (single-line).
FN_DEF_RE = re.compile(r"^\[\^\d+\]:")

# A bibliography entry, as ``reflow/references.py`` leaves it: one entry, one
# paragraph, opening with its own number. Stricter than the rule over there,
# because here there is no reference block around the line to vouch for it — a
# name and a year have to stand in the text itself, or "[3] ist der Beleg für die
# vorstehende Behauptung" would be protected as a citation.
REFERENCE_ENTRY_RE = re.compile(
    r"^\[(\d{1,3})\]\s+[A-ZÄÖÜ].*\b(?:1[5-9]\d\d|20\d\d|21\d\d)\b"
)

# A citation in the running text: "[5]", "[5, 10]", "[18, 20, 29]".
CITATION_RE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")


def anchor_id(number: str) -> str:
    """The name an entry answers to, in both worlds.

    A translated bibliography is a list nothing points at: the markers stay in
    the prose and lead nowhere. So each entry is anchored twice under this one
    name — as an HTML ``id``, which Pandoc and every web renderer follow, and as
    Obsidian's block id at the end of the line. One link target reaches it
    either way, because a circumflex is legal in an HTML id.
    """
    return f"^ref-{number}"

# Confidence flags from the 2-B layer: [?FN:…] / [??FN:…] (optional leading space).
FLAG_RE = re.compile(r" ?\[\?\??FN:[^\]]*\]")

# Existing <dnt>…</dnt> span (transformation applies only outside of it).
_DNT_SPAN_RE = re.compile(r"<dnt>.*?</dnt>", re.DOTALL)
_URL_TRAIL = ".,;:!?)]"


def strip_flags(text: str) -> str:
    """Removes open confidence flags (strip-and-pass, §9-Q2). Body stays
    unchanged; orphaned footnote definitions are preserved."""
    return FLAG_RE.sub("", text)


def strip_dnt(text: str) -> str:
    """Removes the DNT tags, keeps the inner text (round-trip inverse of
    wrapping). Archillator runs this after translation."""
    return text.replace(DNT_OPEN, "").replace(DNT_CLOSE, "")


def _transform_outside_dnt(text: str, transform: Callable[[str], str]) -> str:
    """Applies ``transform`` only to the text parts *outside* existing
    <dnt>…</dnt> spans; existing spans are left untouched. This keeps all
    protect_* functions idempotent and avoids nesting."""
    out: list[str] = []
    last = 0
    for m in _DNT_SPAN_RE.finditer(text):
        out.append(transform(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(transform(text[last:]))
    return "".join(out)


def protect_urls(text: str) -> str:
    """Tags URLs with <dnt>…</dnt>. Trailing punctuation stays outside the
    tag. Skips URLs already tagged."""
    def _wrap(m: re.Match) -> str:
        url = m.group(0)
        trail = ""
        while url and url[-1] in _URL_TRAIL:
            trail = url[-1] + trail
            url = url[:-1]
        return f"{DNT_OPEN}{url}{DNT_CLOSE}{trail}"

    return _transform_outside_dnt(text, lambda s: URL_RE.sub(_wrap, s))


# Function words that belong to one language only. A quotation is a sentence
# of a language, a title rarely more than a noun phrase, and Latin (or Greek)
# must stay as it stands so a translation can go beside it. "et", "in", "la",
# "non", "est", "de" sit in several languages and are left out on purpose: a
# missing word yields no decision, a shared word a wrong one.
FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "de": frozenset("der die das und nicht ist sich des dem den ein eine einer auch wird wurde bei nach aus über durch zu".split()),
    "en": frozenset("the and of to is that it was with which by are this be from have has not".split()),
    "fr": frozenset("le les des une du dans pour pas sur au aux ce sont avec elle nous vous leur était".split()),
    "it": frozenset("il di che è della delle degli gli nel nella sono anche questo più come".split()),
    "es": frozenset("el los las y por para con una del lo como pero más".split()),
    "la": frozenset("quod sed ut cum atque enim nec eius ad ab ex esse quae quam autem vero quoque".split()),
}

# Calibre writes ISO 639-2 ("fra"), the masters mostly 639-1 ("fr").
_LANGUAGE_CODES = {"deu": "de", "ger": "de", "eng": "en", "fra": "fr", "fre": "fr",
                   "ita": "it", "spa": "es", "lat": "la"}

_WORD_RE = re.compile(r"[^\W\d_]+")
_FRONT_LANGUAGE_RE = re.compile(r"^language:\s*\"?([A-Za-z]{2,3})\"?\s*$", re.MULTILINE)

# A quotation in the document's own language is released for translation when
# it reads as a sentence: long, or carrying a stop or semicolon inside. A short
# phrase without one stays protected — it may be a title, and a few untranslated
# words cost the reader little. Measured 2026-11-25 against the masters in
# corpora/books and the Lab (see the commit).
_SENTENCE_WORDS = 13
_SENTENCE_SIGN_RE = re.compile(r";|[^\W\d_]{2}[.!](?:\s|$)")


def word_language(text: str) -> str | None:
    """The language whose own function words the text uses most, or None
    when none, or two equally, are attested."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    scores = {lang: sum(w in fw for w in words) for lang, fw in FUNCTION_WORDS.items()}
    best = max(scores.values())
    if best == 0 or list(scores.values()).count(best) > 1:
        return None
    return max(scores, key=scores.get)


def document_language(markdown: str) -> str | None:
    """`language:` from the front matter, else what the text itself speaks."""
    m = _FRONT_LANGUAGE_RE.search(markdown[:3000]) if markdown.startswith("---") else None
    if m:
        code = m.group(1).lower()
        code = _LANGUAGE_CODES.get(code, code)
        if code in FUNCTION_WORDS:
            return code
    return word_language(markdown)


# Where a quoted span stands as a title: introduced by "in"/"dans", by an
# author in capitals or the dash of a repeated author ("WARTELLE, « … »",
# "———, „…“"); or followed by a comma and, within a few words, "in:", an
# editor, a page range or the year of a publication ("« La charte séleucide
# de Jérusalem », REJ 1935, p. 1"). A quotation is followed by its reference
# in brackets, a semicolon, or nothing.
_TITLE_BEFORE_RE = re.compile(
    r"(?:\b(?:in|In|dans|Dans|en|aus)\s*:?|\b[A-ZÄÖÜÉ][A-ZÄÖÜÉ'-]+,|———,)\s*$"
)
_TITLE_AFTER_RE = re.compile(
    r"^\s*,\s*(?:in|dans|en|im)\b"
    r"|^\s*,[^;]{0,80}?\((?:éds?|eds?|Hrsg|Hg|hg)\.?\)"
    r"|^\s*,[^;()]{0,60}?\b\d{1,4}\s*[-–]\s*\d{1,4}\b"
    r"|^\s*,[^;()]{0,60}?\b(?:1[5-9]\d\d|20\d\d)\b"
)


def is_translatable_quotation(quoted: str, language: str | None,
                              before: str = "", after: str = "") -> bool:
    """A quoted span the reader needs translated: a sentence in the document's
    own language. Titles, short phrases and other languages are not. ``before``
    and ``after`` are the text around the span on its line."""
    if language is None:
        return False
    if _TITLE_BEFORE_RE.search(before) or _TITLE_AFTER_RE.match(after):
        return False
    inner = quoted[1:-1].strip()
    if word_language(inner) != language:
        return False
    return len(inner.split()) >= _SENTENCE_WORDS or bool(_SENTENCE_SIGN_RE.search(inner))


def protect_quoted(text: str, language: str | None = None) -> str:
    """Tags quoted titles (all QUOTE_PAIRS) with <dnt>…</dnt>.
    Only outside existing tags; idempotent. With the document ``language``
    given, a quotation in that language is left free to be translated (see
    is_translatable_quotation)."""
    def _tag(m: re.Match) -> str:
        line = m.string
        if is_translatable_quotation(m.group(0), language,
                                     line[max(0, m.start() - 12):m.start()],
                                     line[m.end():m.end() + 80]):
            return m.group(0)
        return f"{DNT_OPEN}{m.group(0)}{DNT_CLOSE}"

    def _wrap(seg: str) -> str:
        pairs = QUOTE_PAIRS
        # Guillemets point either way: German »…«, French and Italian « … ».
        # The first one in the line tells which; read the wrong way round, the
        # pair would close over the text *between* two quotations.
        first = re.search("[«»]", seg)
        if first and first.group(0) == "«":
            pairs = [p for p in QUOTE_PAIRS if p != ("»", "«")] + [("«", "»")]
        for open_q, close_q in pairs:
            pattern = re.escape(open_q) + "[^" + re.escape(close_q) + "]*" + re.escape(close_q)
            seg = re.sub(pattern, _tag, seg)
        return seg

    return _transform_outside_dnt(text, _wrap)


def prepare_translation(markdown: str) -> str:
    """Master Markdown -> translation-ready MD: strip flags; tag URLs
    everywhere; on footnote-definition lines, additionally tag quoted
    titles. Idempotent; structural Pandoc markers are left untouched."""
    text = strip_flags(markdown)
    language = document_language(text)
    lines = text.split("\n")
    listed = {m.group(1) for line in lines if (m := REFERENCE_ENTRY_RE.match(line))}

    def link_citations(line: str) -> str:
        """Point each citation at its entry. Only what the bibliography lists:
        a count or a year range in brackets stays what it is."""
        def repl(m: re.Match) -> str:
            nums = [n.strip() for n in m.group(1).split(",")]
            if not all(n in listed for n in nums):
                return m.group(0)
            return "[" + ", ".join(f"[{n}](#{anchor_id(n)})" for n in nums) + "]"

        return CITATION_RE.sub(repl, line)

    out_lines: list[str] = []
    for line in lines:
        entry = REFERENCE_ENTRY_RE.match(line)
        if entry:
            # Whole-line protection, and no inner tagging afterwards: a citation
            # is one unit — author, title, venue, year — and every part of it is
            # a thing a translator must leave alone.
            ref = anchor_id(entry.group(1))
            out_lines.append(
                f'<span id="{ref}"></span>{DNT_OPEN}{line}{DNT_CLOSE} {ref}'
            )
            continue
        line = link_citations(line)
        line = protect_urls(line)
        if FN_DEF_RE.match(line):
            line = protect_quoted(line, language)
        out_lines.append(line)
    return "\n".join(out_lines)


BRIEFING = """Translation briefing
====================
This document has been prepared for LLM translation.

1. Translate the running prose into the target language.
2. Leave text inside <dnt>…</dnt> exactly as it stands. Never translate,
   reorder or normalise it. What is protected this way: referenced work and
   article titles, bibliographic references, URLs.
3. Leave untagged work titles, proper names and bibliographic references
   verbatim as well, especially inside the footnote apparatus. When in doubt,
   do not translate. Bibliographic precision outranks completeness.
4. Carry over Pandoc structures unchanged: footnote markers [^N], footnote
   definitions [^N]:, page markers [p. …], region markers [region: …]. A page
   label may be roman ([p. xiv]); it is the page as printed in the book and
   must never be renumbered. A region name is a fixed token of the format —
   leave "[region: bibliography]" exactly so, even where you translate the
   heading beneath it. Leave a leading YAML block (--- … ---) untouched.
5. After translating, remove the <dnt> and </dnt> tags and keep the text
   between them.
"""
