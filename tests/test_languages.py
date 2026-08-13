"""The languages scriptor claims to support, and the proof that it does.

The catalogue is deliberately not a configuration: a missing word produces no
result, never a wrong one (spec §4.4), so switching a language *off* could
only ever cost recognition. See
``docs/internal/2026-08-13-sprachstruktur-design.md``.
"""
import pytest

from scriptor.languages import NOT_ATTESTED, SUPPORTED_LANGUAGES
from scriptor.reflow.regions import REGION_NAMES, _VOCABULARY

# `main` names the running text and has no heading of its own; `front-matter`
# is set by the page mode, not by a word. Neither carries vocabulary.
_WITHOUT_VOCABULARY = ("main", "front-matter")
_WITH_VOCABULARY = tuple(r for r in REGION_NAMES if r not in _WITHOUT_VOCABULARY)


def test_language_codes_are_iso_639_1():
    assert SUPPORTED_LANGUAGES == ("de", "en", "fr", "it", "es", "pt",
                                   "nl", "ru", "la")
    assert all(len(c) == 2 and c.islower() for c in SUPPORTED_LANGUAGES)
    assert len(set(SUPPORTED_LANGUAGES)) == len(SUPPORTED_LANGUAGES)


def test_not_attested_is_distinguishable_from_an_empty_entry():
    """The whole mechanism rests on this. Were NOT_ATTESTED an empty tuple, a
    deliberate blank would read exactly like a forgotten one, and the
    completeness test could not tell "checked, does not exist" from "nobody
    got round to it"."""
    assert not isinstance(NOT_ATTESTED, tuple)
    assert NOT_ATTESTED != ()
    assert repr(NOT_ATTESTED) == "NOT_ATTESTED"


# ── completeness ─────────────────────────────────────────────────────

@pytest.mark.parametrize("region", _WITH_VOCABULARY)
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_language_answers_for_every_region(language, region):
    """The mechanism this file exists for.

    Adding a tenth language turns this red once per region, and each failure
    names the decision that is still missing — rather than letting a language
    be half-added, which is how "Inhoud" went missing and "SOMMARIO" nearly
    did.
    """
    entry = _VOCABULARY[region]
    assert language in entry, (
        f"{region}/{language}: kein Eintrag. Entweder Muster ergänzen oder "
        f"ausdrücklich NOT_ATTESTED setzen."
    )
    patterns = entry[language]
    assert patterns is NOT_ATTESTED or (
        isinstance(patterns, tuple) and len(patterns) > 0
    ), f"{region}/{language}: leerer Eintrag — NOT_ATTESTED sagt, was gemeint ist."


def test_no_language_outside_the_catalogue():
    for region, entry in _VOCABULARY.items():
        unknown = set(entry) - set(SUPPORTED_LANGUAGES)
        assert not unknown, f"{region}: unbekannte Sprache(n) {sorted(unknown)}"


def test_no_language_is_attested_nowhere():
    """A language whose every entry is NOT_ATTESTED is not supported, it is
    merely listed."""
    for language in SUPPORTED_LANGUAGES:
        attested = [
            region for region in _WITH_VOCABULARY
            if _VOCABULARY[region].get(language) is not NOT_ATTESTED
        ]
        assert attested, f"{language}: nirgends belegt, gehört nicht in den Katalog"


def test_every_region_with_vocabulary_is_a_spec_name():
    assert set(_VOCABULARY) <= set(REGION_NAMES)
