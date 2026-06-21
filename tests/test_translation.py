"""Tests für das Übersetzungs-Profil (Etappe 2c).

Markdown-Postprozessor: schützt nicht zu übersetzende Elemente mit
<dnt>…</dnt>-Tags (URLs überall; Titel in Anführungszeichen im Fußnoten-
apparat) und entfernt offene Confidence-Flags (strip-and-pass).
"""

from scriptor.reflow.translation import (
    strip_flags,
    strip_dnt,
    protect_urls,
    protect_quoted,
    prepare_translation,
    BRIEFING,
)


# --- strip_flags --------------------------------------------------------------

def test_strip_flags_removes_orphan_and_inline_flags():
    src = "Ein Wort A[?FN:4|A] und ein Satz. [?FN:7] [^3] [S. 12]"
    assert strip_flags(src) == "Ein Wort A und ein Satz. [^3] [S. 12]"


def test_strip_flags_removes_geraten_multiflag():
    src = "Text B[??FN:3|B:0.6] mehr 8[??FN:3|8:0.4] Ende."
    assert strip_flags(src) == "Text B mehr 8 Ende."


# --- strip_dnt ----------------------------------------------------------------

def test_strip_dnt_removes_tags_keeps_inner_text():
    src = 'Vgl. <dnt>„Römische Geschichte“</dnt>, Berlin <dnt>http://x.org</dnt>.'
    assert strip_dnt(src) == 'Vgl. „Römische Geschichte“, Berlin http://x.org.'


def test_strip_dnt_noop_without_tags():
    assert strip_dnt("kein Tag hier") == "kein Tag hier"


# --- protect_urls -------------------------------------------------------------

def test_protect_urls_wraps_bare_url():
    src = "Online unter https://example.org/a verfügbar."
    assert protect_urls(src) == "Online unter <dnt>https://example.org/a</dnt> verfügbar."


def test_protect_urls_strips_trailing_punctuation_outside_tag():
    src = "Siehe www.example.org/b."
    assert protect_urls(src) == "Siehe <dnt>www.example.org/b</dnt>."


def test_protect_urls_idempotent():
    once = protect_urls("x http://a.org y")
    assert protect_urls(once) == once


def test_protect_urls_skips_url_already_in_dnt():
    src = "k <dnt>http://a.org</dnt> z"
    assert protect_urls(src) == src


# --- protect_quoted -----------------------------------------------------------

def test_protect_quoted_german_low_high():
    src = 'Vgl. Mommsen, „Römische Geschichte“, Berlin.'
    assert protect_quoted(src) == 'Vgl. Mommsen, <dnt>„Römische Geschichte“</dnt>, Berlin.'


def test_protect_quoted_straight_and_guillemets():
    assert protect_quoted('a "Titel" b') == 'a <dnt>"Titel"</dnt> b'
    assert protect_quoted("a »Titel« b") == "a <dnt>»Titel«</dnt> b"


def test_protect_quoted_two_phrases():
    src = 'x „A“ und „B“ y'
    assert protect_quoted(src) == 'x <dnt>„A“</dnt> und <dnt>„B“</dnt> y'


def test_protect_quoted_idempotent():
    once = protect_quoted('„Titel“')
    assert protect_quoted(once) == once


# --- prepare_translation (Orchestrierung) -------------------------------------

def test_prepare_apparatus_vs_body_asymmetry():
    body = 'Er nannte „Römische Geschichte“ ein Werk.'
    fndef = '[^3]: Vgl. „Römische Geschichte“, Berlin 1854.'
    out = prepare_translation(body + "\n" + fndef).split("\n")
    assert out[0] == body  # Body unverändert
    assert out[1] == '[^3]: Vgl. <dnt>„Römische Geschichte“</dnt>, Berlin 1854.'


def test_prepare_urls_everywhere():
    src = "Body http://a.org\n[^1]: Def www.b.org/x"
    out = prepare_translation(src).split("\n")
    assert out[0] == "Body <dnt>http://a.org</dnt>"
    assert out[1] == "[^1]: Def <dnt>www.b.org/x</dnt>"


def test_prepare_strips_flags():
    src = "Wort A[?FN:4|A] hier.\n[^5]: Text."
    out = prepare_translation(src)
    assert "[?FN" not in out and "Wort A hier." in out


def test_prepare_idempotent():
    src = '[^3]: Vgl. „Titel“, http://a.org.\nBody.'
    once = prepare_translation(src)
    assert prepare_translation(once) == once


def test_prepare_roundtrip_equals_strip_flags():
    # strip_dnt(prepare(x)) == strip_flags(x): Tagging restlos reversibel.
    src = '[^3]: „Titel“ http://a.org [?FN:4|A]\nBody „Zitat“.'
    assert strip_dnt(prepare_translation(src)) == strip_flags(src)


def test_prepare_balanced_tags():
    src = '[^3]: „A“ und „B“ http://x.org\nBody.'
    out = prepare_translation(src)
    assert out.count("<dnt>") == out.count("</dnt>")


# --- BRIEFING -----------------------------------------------------------------

def test_briefing_mentions_convention_and_removal():
    assert "<dnt>" in BRIEFING and "</dnt>" in BRIEFING
    assert "ungetaggt" in BRIEFING.lower()
    assert "entfern" in BRIEFING.lower()
