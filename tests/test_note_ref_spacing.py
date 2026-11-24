"""A footnote reference stands as a word of its own, one space on each side."""

import pytest

from scriptor._text import space_note_refs


@pytest.mark.parametrize("given, wanted", [
    # the rule
    ("period.[^6] The", "period. [^6] The"),
    ("period. [^6]The", "period. [^6] The"),
    ("period.   [^6]   The", "period. [^6] The"),
    # a run of references
    ("over them. [^16][^17] The", "over them. [^16] [^17] The"),
    ("Palestine [^2] [^3][^4] It", "Palestine [^2] [^3] [^4] It"),
    # close before punctuation and closing brackets, and at a line's end
    ("(see p. 4[^5]) and", "(see p. 4 [^5]) and"),
    ("the text [^5] , then", "the text [^5], then"),
    ("ends here.[^5]  \nNext", "ends here. [^5]\nNext"),
    ("ends here.[^5]", "ends here. [^5]"),
    # close after an opening bracket
    ("([^5] see", "([^5] see"),
    # quotes that open in one language and close in another stay as they were
    ("„Zitat“[^5] weiter", "„Zitat“[^5] weiter"),
    ("said[^5]» und", "said [^5]» und"),
    ("merits.” [^60] Then", "merits.” [^60] Then"),
    # a literal marker the source printed
    ("[^614][^615]\\* May", "[^614] [^615] \\* May"),
    # definitions, indents and headings
    ("[^5]: The note.", "[^5]: The note."),
    ("    [^5] text", "    [^5] text"),
    ("# Charter of 804[^460]", "# Charter of 804 [^460]"),
    # page markers are words too
    ("[p. 12][^5] and", "[p. 12] [^5] and"),
])
def test_spacing(given, wanted):
    assert space_note_refs(given) == wanted


def test_idempotent():
    text = "A.[^1] B [^2][^3]) C[^4]\n\n[^1]: x"
    once = space_note_refs(text)
    assert space_note_refs(once) == once
