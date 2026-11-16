"""Small type cut from a page of front matter is text, not a note."""

from scriptor.reflow.core import Page, front_matter_notes_as_text


def _page(index, mode, body, footnotes):
    p = Page(num=index, body_lines=list(body), footnotes=dict(footnotes))
    p.index, p.mode = index, mode
    return p


def test_an_imprint_cut_as_a_note_goes_back_as_printed():
    # Fried, *Karl der Große* p. 4: "1. Auflage. 2013" in 8pt, read as note 1.
    imprint = ["1. Auflage. 2013", "© Verlag C.H.Beck oHG, München 2013"]
    pages = [_page(4, "frontmatter", ["Mit 60 Abbildungen im Text"],
                   {1: "Auflage. 2013 © Verlag C.H.Beck oHG, München 2013"})]
    assert front_matter_notes_as_text(pages, [None, None, None, imprint]) == 1
    assert pages[0].footnotes == {}
    assert pages[0].body_lines == ["Mit 60 Abbildungen im Text", *imprint]


def test_without_a_cut_block_the_notes_go_back_as_lines():
    pages = [_page(2, "frontmatter", ["Widmung"], {1: "Für A."})]
    front_matter_notes_as_text(pages, [None, None])
    assert pages[0].body_lines == ["Widmung", "1 Für A."]


def test_a_page_of_the_text_keeps_its_notes():
    pages = [_page(9, "main", ["Text.1"], {1: "Eine Note."})]
    assert front_matter_notes_as_text(pages, [None] * 9) == 0
    assert pages[0].footnotes == {1: "Eine Note."}
