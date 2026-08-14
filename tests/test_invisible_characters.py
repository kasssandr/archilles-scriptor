"""Characters the reader never sees, and what they cost when they survive.

Three kinds arrive from real PDFs, and they need three different answers:

*Soft hyphens* (U+00AD) mark where a word was broken across lines. They carry
better information than a plain "-", which might be a compound hyphen -- a soft
hyphen never is. Artificial Humanities, typeset in InDesign, breaks 1141 words
this way; in 1140 of them the halves came out as two words with a space between
("unprece\xad dented"), because the de-hyphenation only ever looked for U+002D.

*Zero-width marks* (U+200B, U+200C, U+FEFF) are break opportunities the
typesetter left for the renderer. They mean nothing in the text and must go --
4643 of them stood in one master, splitting words for anyone searching it.

*Control characters* mean a broken encoding. The Oxford Handbook maps its fi and
fl ligatures onto U+007F and U+0080, so "figures" arrives as "\x7fgures" and the
font's own ToUnicode table maps both to U+0000: the file itself does not know
what they are. What the document does know is spelling -- where "first" also
occurs unbroken, "\x7frst" is proof that U+007F is "fi". That evidence is
counted per character over the whole document, never guessed per word.
"""

from scriptor.reflow.characters import (
    SOFT_HYPHEN,
    learn_broken_glyphs,
    resolve_characters,
)


# --- soft hyphens -------------------------------------------------------------

def test_a_soft_hyphen_at_a_line_end_becomes_a_line_break_hyphen():
    # It stays a hyphen rather than joining here: the join is reconstruct_body's
    # decision, and it already knows how to make it.
    pages = [["unprece" + SOFT_HYPHEN, "dented power"]]
    out, _ = resolve_characters(pages)
    assert out == [["unprece-", "dented power"]]


def test_a_soft_hyphen_inside_a_line_just_goes():
    # Nothing was broken here; the mark is an unused break opportunity.
    pages = [["unprece" + SOFT_HYPHEN + "dented power"]]
    out, _ = resolve_characters(pages)
    assert out == [["unprecedented power"]]


def test_a_soft_hyphen_after_trailing_space_still_counts_as_a_line_end():
    pages = [["unprece" + SOFT_HYPHEN + "  ", "dented"]]
    out, _ = resolve_characters(pages)
    assert out[0][0].rstrip() == "unprece-"


# --- zero-width marks ---------------------------------------------------------

def test_zero_width_marks_are_removed():
    pages = [["human​based and post‌human﻿"]]
    out, _ = resolve_characters(pages)
    assert out == [["humanbased and posthuman"]]


# --- broken encodings ---------------------------------------------------------

def test_a_control_character_is_read_off_the_documents_own_spelling():
    # Two words the document also writes out unbroken are enough to say what
    # U+007F is -- and the reading then repairs the words it never wrote out,
    # which is the whole point: a file that breaks a ligature breaks it
    # everywhere, so "scientific" has no intact twin anywhere in it.
    pages = [
        ["the first century, a field of study"],
        ["in the \x7frst place, across the \x7feld"],
        ["scienti\x7fc and speci\x7fc"],
    ]
    assert learn_broken_glyphs(pages) == {"\x7f": "fi"}
    out, report = resolve_characters(pages)
    assert out[1] == ["in the first place, across the field"]
    assert out[2] == ["scientific and specific"]
    assert report.resolved == {"\x7f": "fi"}


def test_a_control_character_nothing_vouches_for_is_dropped_and_reported():
    # Dropping is not a repair -- it is the honest answer where the document
    # offers no evidence, and the report is how anyone finds out.
    pages = [["a stray \x15 mark"], ["another \x15 one"]]
    out, report = resolve_characters(pages)
    assert out == [["a stray  mark"], ["another  one"]]
    assert report.resolved == {}
    assert report.dropped == {"\x15": 2}


def test_one_stray_spelling_does_not_establish_a_ligature():
    # A single word form is a coincidence, not evidence. Counted in distinct
    # forms rather than occurrences: one word repeated forty times still says
    # only what that one word says (MIN_GLYPH_EVIDENCE).
    pages = [["fist"], ["\x7fst"], ["\x7fst"], ["\x7fst"]]
    assert learn_broken_glyphs(pages) == {}


def test_the_stronger_reading_wins_where_two_are_possible():
    # "\x7frst" reads as both "first" and "strst"-nonsense; only the words the
    # document itself writes out decide. Here "fi" is vouched for by three
    # forms and "st" by one.
    pages = [
        ["first field defined"],
        ["fist"],
        ["\x7frst"], ["\x7feld"], ["de\x7fned"], ["\x7fst"],
    ]
    assert learn_broken_glyphs(pages) == {"\x7f": "fi"}


def test_a_ligature_may_not_vouch_for_itself():
    """Asclepios: a control character sat at the end of numbered lines ("8\\x08",
    "10\\x08"), and reading it as "st" turned "8\\x08" into "8st". A word pattern
    that skips digits then reports the word "st" -- which the document does
    write out -- so the reading proved itself with its own output. Forty such
    lines were enough to establish it.

    Two things stop that: a damaged form has to be a word (letters and the
    damaged character, nothing else), and the repair has to be longer than the
    ligature it inserted.
    """
    pages = [["st"], ["8\x08"], ["10\x08"], ["12\x08"], ["14\x08"]]
    assert learn_broken_glyphs(pages) == {}
    out, report = resolve_characters(pages)
    assert out[1] == ["8"]
    assert report.dropped == {"\x08": 4}


def test_a_reading_must_leave_more_behind_than_the_ligature():
    # "ff" is a word of the document; that must not make every stray character
    # sitting alone read as "ff".
    pages = [["off and off again"], ["\x15"], ["\x15"], ["\x15"]]
    assert learn_broken_glyphs(pages) == {}


def test_a_document_without_invisibles_is_returned_unchanged():
    pages = [["Ganz gewoehnlicher Text."], ["Zweite Seite."]]
    out, report = resolve_characters(pages)
    assert out == pages
    assert report.resolved == {} and report.dropped == {}
    assert report.soft_hyphens == 0


def test_the_report_counts_what_it_did():
    pages = [["bro" + SOFT_HYPHEN, "ken​word \x15"]]
    _out, report = resolve_characters(pages)
    assert report.soft_hyphens == 1
    assert report.zero_width == 1
    assert report.dropped == {"\x15": 1}
