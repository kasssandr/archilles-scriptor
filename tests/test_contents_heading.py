"""The heading a table of contents prints over itself.

A contents list is not recognised by where it stands -- four of the eighteen
corpus volumes carry one at the back -- nor by a confidence threshold, which
overlaps between real contents (0.45 at Making Martyrs) and name registers
(0.53 at Themistios). It is recognised by what the volume writes over it, and
the user's observation is that this holds without exception: no contents page
carries the book's title, every one carries "Índice" or its equivalent.

The vocabulary for that already exists (regions.region_of_heading knows
Sumário, TABLE DES MATIÈRES, Inhoudsopgave, Содержание …). What it cannot read
is the two shapes a printer gives such a heading.
"""

from scriptor.reflow.toc import is_contents_heading


def test_a_plain_heading_is_read():
    assert is_contents_heading("Inhoudsopgave")
    assert is_contents_heading("TABLE DES MATIÈRES")
    assert is_contents_heading("Содержание")


def test_a_letterspaced_heading_is_read():
    # A comemoração sets it as 'S u m á r i o'. Letterspacing is a typographic
    # emphasis, not a different word, and the extractor hands over what the
    # page holds -- single letters with spaces between them.
    assert is_contents_heading("S u m á r i o")
    assert is_contents_heading("I N H A L T")


def test_a_heading_with_its_own_page_number_is_read():
    # Les apologistes prints 'TABLE DES MATIÈRES  353' -- the running head of
    # the contents, folio and all.
    assert is_contents_heading("TABLE DES MATIÈRES  353")
    assert is_contents_heading("353  TABLE DES MATIÈRES")


def test_ordinary_prose_is_not_a_heading():
    assert not is_contents_heading("Die Ergebnisse der Untersuchung zeigen")
    assert not is_contents_heading("")
    assert not is_contents_heading("Register van personen, plaatsen en zaken")


def test_letterspacing_does_not_invent_words():
    # Spacing out is only undone where nearly every token is a single letter;
    # otherwise "I. Die Antike" would collapse into nonsense.
    assert not is_contents_heading("I. Die Antike als Vorbild")
