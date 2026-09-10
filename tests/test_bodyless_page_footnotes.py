"""A page that holds nothing but notes still belongs to the document.

Baltrusch, *Die Juden und das Römische Reich*, sets its endnotes entirely in
small type under a body-size running head. ``split_small_type_block`` takes
everything below the head for the page's footnote block, the running head is
stripped, and the page reaches ``reconstruct_body`` with no body and a dozen or
more definitions. ``reconstruct_body`` skipped every page without a body -- and
with it the rescue for unclaimed notes, which names this very case ("Page
contains only footnote definitions without its own body"). 33 pages of notes,
a fifth of the volume, vanished; the master carried 14 definitions where the
audit of the same run counted 392.

The rescue parks such notes on the next paragraph. ``end_paragraph`` then
wiped them whenever it closed a paragraph that had no text -- an empty line at
the head of the next page, a chapter heading -- so of a run of note pages only
the last survived, and notes on the last page of a volume had no next
paragraph at all.
"""

from scriptor.reflow.core import Page, reconstruct_body

PROSE = [
    "Ein langer Satz des Brottextes zieht sich ueber die ganze Zeile",
    "hin und laeuft weiter, damit hier ein Absatz entsteht.",
]


def _body(index, lines=PROSE, **kw):
    return Page(num=-1, index=index, mode="main", label=str(index),
                body_lines=list(lines), **kw)


def _notes_only(index, footnotes):
    return Page(num=-1, index=index, mode="main", label=str(index),
                body_lines=[], footnotes=footnotes)


def _texts(fns):
    return sorted(t for d in fns for t in d.values())


def test_the_notes_of_a_page_without_body_survive():
    _paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {22: "Ben Sira 50, 1-21."}), _body(3)],
        threshold=40)
    assert _texts(fns) == ["Ben Sira 50, 1-21."]


def test_the_notes_of_consecutive_pages_without_body_all_survive():
    _paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1),
         _notes_only(2, {44: "F. Harper (1892-1914), S. 633."}),
         _notes_only(3, {62: "Esr. 4, 1-5."}),
         _notes_only(4, {80: "Neh. 2, 11."}),
         _body(5)],
        threshold=40)
    assert _texts(fns) == ["Esr. 4, 1-5.", "F. Harper (1892-1914), S. 633.",
                           "Neh. 2, 11."]


def test_parked_notes_survive_an_empty_line_opening_the_next_page():
    _paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {7: "Jos. ant. 12, 145f."}),
         _body(3, lines=[""] + PROSE)],
        threshold=40)
    assert _texts(fns) == ["Jos. ant. 12, 145f."]


def test_parked_notes_survive_a_chapter_heading_on_the_next_page():
    _paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {8: "Polyb. 29, 10."}),
         _body(3, heading="III. Rom und die Juden")],
        threshold=40)
    assert _texts(fns) == ["Polyb. 29, 10."]


def test_the_notes_of_a_last_page_without_body_survive():
    # No next paragraph exists; the notes go to the last one there is.
    _paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {9: "Cic. prov. cons. 31."})],
        threshold=40)
    assert _texts(fns) == ["Cic. prov. cons. 31."]


def test_a_page_with_neither_body_nor_notes_adds_nothing():
    paras, fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {}), _body(3)], threshold=40)
    assert _texts(fns) == []
    assert all(p.strip() for p in paras)


def test_a_page_without_body_lends_its_label_to_no_other_page():
    # Its page marker has no word to stand before. Left pending, it would be
    # placed before the first word of the next page -- and where that page
    # carries no label of its own, its text would be cited under the wrong
    # page. A missing marker is a gap; a wrong one is a false citation.
    unlabelled = Page(num=-1, index=3, mode="main", label=None,
                      body_lines=list(PROSE))
    paras, _fns, _occ, _lvl = reconstruct_body(
        [_body(1), _notes_only(2, {22: "Eine Note."}), unlabelled],
        threshold=40)
    assert not any("[p. 2]" in p for p in paras)


def test_notes_of_a_page_without_body_are_audited():
    audit: dict[str, list[int]] = {}
    reconstruct_body([_body(1), _notes_only(2, {22: "Eine Note."}), _body(3)],
                     threshold=40, audit=audit)
    assert audit == {"2": [22]}
