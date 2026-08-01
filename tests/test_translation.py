"""Tests for the translation profile (stage 2c).

Markdown post-processor: protects elements that must not be translated with
<dnt>…</dnt> tags (URLs everywhere; quoted titles in the footnote apparatus)
and removes open confidence flags (strip-and-pass).
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
    src = "Ein Wort A[?FN:4|A] und ein Satz. [?FN:7] [^3] [p. 12]"
    assert strip_flags(src) == "Ein Wort A und ein Satz. [^3] [p. 12]"


def test_strip_flags_removes_guessed_multiflag():
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


# --- prepare_translation (orchestration) -------------------------------------

def test_prepare_apparatus_vs_body_asymmetry():
    body = 'Er nannte „Römische Geschichte“ ein Werk.'
    fndef = '[^3]: Vgl. „Römische Geschichte“, Berlin 1854.'
    out = prepare_translation(body + "\n" + fndef).split("\n")
    assert out[0] == body  # body unchanged
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
    # strip_dnt(prepare(x)) == strip_flags(x): tagging is fully reversible.
    src = '[^3]: „Titel“ http://a.org [?FN:4|A]\nBody „Zitat“.'
    assert strip_dnt(prepare_translation(src)) == strip_flags(src)


def test_prepare_balanced_tags():
    src = '[^3]: „A“ und „B“ http://x.org\nBody.'
    out = prepare_translation(src)
    assert out.count("<dnt>") == out.count("</dnt>")


# --- BRIEFING -----------------------------------------------------------------

def test_briefing_mentions_convention_and_removal():
    assert "<dnt>" in BRIEFING and "</dnt>" in BRIEFING
    assert "untagged" in BRIEFING.lower()
    assert "remove" in BRIEFING.lower()


# --- REFERENCE ENTRIES --------------------------------------------------------

def test_a_reference_entry_is_protected_whole():
    """Sen et al. [23]: without protection a translator renders "BEIR: A
    Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval
    Models" into German and the citation stops being findable."""
    src = (
        "[23] Nandan Thakur, Nils Reimers, and Iryna Gurevych. 2021. BEIR: A "
        "Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval "
        "Models. In Advances in Neural Information Processing Systems."
    )

    out = prepare_translation(src)

    assert out == f'<span id="^ref-23"></span><dnt>{src}</dnt> ^ref-23'


def test_protecting_a_reference_entry_is_idempotent():
    src = "[7] Zhengbao Jiang. 2023. Active Retrieval Augmented Generation. https://x.org"
    once = prepare_translation(src)
    assert prepare_translation(once) == once
    assert once.count("<dnt>") == once.count("</dnt>") == 1


def test_a_footnote_marker_in_prose_is_not_a_reference_entry():
    """Body text opens with a placed marker often enough; it is not a citation."""
    src = "[3] ist der Beleg für die vorstehende Behauptung im laufenden Text."
    assert prepare_translation(src) == src


def test_reference_entries_are_anchored_for_both_renderers():
    """An entry carries the same name twice: an HTML id every renderer follows,
    and Obsidian's block id at the end of the line. One link target serves both,
    because a circumflex is legal in an HTML id."""
    src = "[5] Yunfan Gao and Yun Xiong. 2024. Retrieval-Augmented Generation."

    out = prepare_translation(src)

    assert out.startswith('<span id="^ref-5"></span><dnt>[5] Yunfan Gao')
    assert out.endswith("</dnt> ^ref-5")


def test_citations_in_the_prose_become_links():
    src = (
        "[5] Yunfan Gao. 2024. Retrieval-Augmented Generation.\n"
        "[10] Patrick Lewis. 2020. Retrieval-Augmented Generation for NLP.\n"
        "Agenten nutzen Wissen zur Inferenzzeit [5, 10], um zu schliessen."
    )

    out = prepare_translation(src).split("\n")[2]

    assert out == (
        "Agenten nutzen Wissen zur Inferenzzeit "
        "[[5](#^ref-5), [10](#^ref-10)], um zu schliessen."
    )


def test_a_number_without_an_entry_is_left_alone():
    """Only what the bibliography actually lists becomes a link — a year range or
    a count in brackets stays what it is."""
    src = "[5] Yunfan Gao. 2024. Retrieval.\nDie Stichprobe umfasst [116] Fragen."

    assert prepare_translation(src).split("\n")[1] == "Die Stichprobe umfasst [116] Fragen."
