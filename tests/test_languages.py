"""The languages scriptor claims to support, and the proof that it does.

The catalogue is deliberately not a configuration: a missing word produces no
result, never a wrong one (spec §4.4), so switching a language *off* could
only ever cost recognition. See
``docs/internal/2026-08-13-sprachstruktur-design.md``.
"""
from scriptor.languages import NOT_ATTESTED, SUPPORTED_LANGUAGES


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
