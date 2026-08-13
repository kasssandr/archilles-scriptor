"""The languages scriptor supports, in one place.

Scriptor's language knowledge is *recognition vocabulary*, and its economics
are asymmetric: a missing word yields no result, never a wrong one (spec
§4.4). So this is a catalogue, not a configuration — nothing here switches a
language off, and every language applies to every volume at once.

That is safe for headings, and measurably so: the sixty-six literal patterns
of the region vocabulary collide nowhere, because each must match a whole
line of at most forty-eight characters, and only the first six lines of a
page are ever offered. It is emphatically *not* safe for a rule that reaches
into running text — see ``KEEP_HYPHEN_BEFORE`` in ``reflow/core.py``, which
stays German for a reason that was measured rather than assumed.

Archilles solves a different problem with a similar-looking list: its
``get_languages()`` configures *behaviour* — interface language, corpus
filter — and may legitimately exclude. The two are deliberately not merged.
"""

from __future__ import annotations

# ISO 639-1, plus `la`: scholarly editions title their indices in Latin
# ("index nominum", "conspectus librorum"), which is why it is here — not
# because Latin volumes are expected.
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "de", "en", "fr", "it", "es", "pt", "nl", "ru", "la",
)


class _NotAttested:
    """Checked, and not attested in the corpus — as opposed to forgotten.

    Deliberately not an empty tuple: a blank meaning "this language has no
    such heading" must not read like one meaning "nobody has filled this in
    yet", or the completeness test protects nothing.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_ATTESTED"

    def __bool__(self) -> bool:
        return False


NOT_ATTESTED = _NotAttested()
