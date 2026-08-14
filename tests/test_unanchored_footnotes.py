"""A footnote whose marker was lost still belongs to the document.

``reconstruct_body`` rescues the definitions no marker claimed by hanging them
off the last paragraph the page touched. That rescue used to be conditional on
the page carrying a printed label, because the same branch also files the page
under its label in the audit -- and a page with no label filed nothing and kept
nothing. What a page is *called* has nothing to do with whether its text
survives, and volumes exist where no page is called anything at all: two of the
sixteen corpus volumes yield no page label whatsoever, so every unclaimed note
in them was dropped without a trace.
"""

from scriptor.reflow.core import Page, reconstruct_body


def _page(label, note):
    return Page(
        num=-1, index=1, mode="main", label=label,
        body_lines=[
            "Ein langer Satz des Brottextes zieht sich ueber die ganze Zeile",
            "hin und laeuft weiter, damit hier ein Absatz entsteht.",
        ],
        footnotes={2: note},
    )


def _texts(fns):
    return [t for d in fns for t in d.values()]


def test_an_unclaimed_note_survives_on_a_labelled_page():
    _paras, fns, _occs, _levels = reconstruct_body(
        [_page("77", "ARISTIDE, Apol. 1, 1.")], threshold=40)
    assert _texts(fns) == ["ARISTIDE, Apol. 1, 1."]


def test_an_unclaimed_note_survives_on_a_page_without_a_label():
    _paras, fns, _occs, _levels = reconstruct_body(
        [_page(None, "ARISTIDE, Apol. 1, 1.")], threshold=40)
    assert _texts(fns) == ["ARISTIDE, Apol. 1, 1."]


def test_the_audit_still_names_the_page_it_can_name():
    audit: dict[str, list[int]] = {}
    reconstruct_body([_page("77", "Eine Note.")], threshold=40, audit=audit)
    assert audit == {"77": [2]}


def test_an_unlabelled_page_is_audited_by_its_physical_position():
    # The reader has to be able to find the page. Without a printed label the
    # only handle left is where it sits in the file sequence, and saying so is
    # better than saying nothing.
    audit: dict[str, list[int]] = {}
    reconstruct_body([_page(None, "Eine Note.")], threshold=40, audit=audit)
    assert audit == {"phys. 1": [2]}
