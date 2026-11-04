"""White ink on the bare page is in the file and not on the page; it is not read.

Fried's Donation of Constantine (Word, De Gruyter 2007) carries its footnote
separator as a white "h" above every apparatus and sets a white "1" or "11"
before each page number of its contents, so the text layer said "135" where the
page shows 35, and eight chapters went without their heading.
"""

import pymupdf

from scriptor.extract import pymupdf_backend

WHITE = (1, 1, 1)


def _page(build):
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    build(page)
    return doc, page


def _read(page):
    unseen: list[str] = []
    return pymupdf_backend.read_page(page, 1, unseen=unseen), unseen


def test_white_ink_between_leader_and_page_number_is_not_read():
    def build(page):
        lead = "Introduction ......"
        page.insert_text((20, 60), lead, fontsize=9)
        x = 20 + pymupdf.get_text_length(lead, fontsize=9)
        page.insert_text((x, 60), "11", fontsize=9, color=WHITE)
        x += pymupdf.get_text_length("11", fontsize=9)
        page.insert_text((x, 60), "1", fontsize=9)

    doc, page = _page(build)
    model, unseen = _read(page)
    # The page shows a gap where the white digits stood, and the gap is what
    # lets the contents parser find the page number.
    assert [ln.text for ln in model.lines] == ["Introduction ...... 1"]
    assert unseen == ["11"]
    doc.close()


def test_a_white_separator_glyph_leaves_no_line():
    def build(page):
        page.insert_text((20, 60), "the last line of the text", fontsize=9)
        page.insert_text((20, 80), "                h", fontsize=9, color=WHITE)
        page.insert_text((20, 100), "1  The first note.", fontsize=7)

    doc, page = _page(build)
    model, unseen = _read(page)
    assert [ln.text for ln in model.lines] == ["the last line of the text",
                                               "1  The first note."]
    assert unseen == ["h"]
    doc.close()


def test_white_ink_on_a_dark_ground_is_printed_and_read():
    def build(page):
        page.draw_rect(pymupdf.Rect(20, 40, 280, 90), fill=(0.15, 0.15, 0.3))
        page.insert_text((30, 70), "A Title Set Light on Dark", fontsize=14, color=WHITE)

    doc, page = _page(build)
    model, unseen = _read(page)
    assert [ln.text for ln in model.lines] == ["A Title Set Light on Dark"]
    assert unseen == []
    doc.close()
