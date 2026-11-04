"""An edition set in small type, with numbered paragraphs and a line count.

Fried, *Donation of Constantine and Constitutum Constantini* (De Gruyter 2007),
appendix B: Fuhrmann's Constitutum Constantini and its translation, in 9.5 pt
against a 10.5 pt body. The first page of each, under its title alone, went
into the notes; every "4. Nam sapiens retro semper" became a chapter; and the
count in the margin stood in the text ("ab omni30 bus").
"""

from scriptor.page import Box, Line, SourcePage, Span
from scriptor.reflow.core import Page, reconstruct_body
from scriptor.reflow.footnotes import split_small_type_block
from scriptor.reflow.textlines import reconstruct

EDITION = [
    "1. In the name of the holy and indivisible Trinity, the Father, namely, and",
    "the Son and the Holy Spirit. The emperor Caesar Flavius Constantine in",
    "2. Our most gracious serenity desires, in clear discourse, through the page",
    "of this our imperial decree, to bring to the knowledge of all the people.",
]


def test_a_page_set_small_under_its_title_alone_is_no_apparatus():
    lines = ["II. The “Constitutum Constantini” in translation", *EDITION]
    sizes = [12.0] + [9.48] * len(EDITION)
    assert split_small_type_block(lines, sizes, body_size=10.5) is None


def test_a_note_on_a_title_alone_is_still_the_apparatus():
    # A page that holds nothing but a title and the title's note: the marker
    # in the title says the small type below is its apparatus.
    lines = ["Appendix A: The Satraps of Constantine¹",
             "1 Wolfram Brandes, Finanzverwaltung in Krisenzeiten, Frankfurt/Main 2002."]
    split = split_small_type_block(lines, [14.04, 8.52], body_size=10.5)
    assert split is not None and split.notes == lines[1:]


def _body_page(lines):
    return Page(num=-1, index=1, mode="main", label="130", body_lines=list(lines))


def test_a_numbered_paragraph_that_runs_on_is_no_heading():
    paras, _f, _o, levels = reconstruct_body([_body_page([
        "4. Nam sapiens retro semper",
        "deus edidit ex se, per quod semper erant gignenda saecula, verbum.",
        "15. Viris enim reverentissimis, clericis diversis ordinibus eidem sacro-",
        "sanctae Romanae ecclesiae servientibus illud culmen habere sancimus.",
    ])], threshold=70)
    assert levels == [0, 0]
    assert paras[0].startswith("[p. 130] 4. Nam sapiens retro semper deus edidit")
    assert paras[1].startswith("15. Viris enim reverentissimis, clericis diversis "
                               "ordinibus eidem sacrosanctae")


def test_a_numbered_heading_is_still_a_heading():
    _p, _f, _o, levels = reconstruct_body([_body_page([
        "3.4. Probleme um Welf VI.",
        "Die Frage nach dem Erbe stellte sich erst spät.",
    ])], threshold=40)
    assert levels == [2, 0]


def _frag(text, x0, baseline, x1=None):
    x1 = x1 if x1 is not None else x0 + 5 * len(text)
    box = Box(x0, baseline - 7.0, x1, baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=9.48)], box=box, baseline=baseline)


def _edition_page(numbers_x0, *, step=5, first=30):
    """A verso of Fuhrmann's edition: text at 140.9, the count beside it."""
    lines = [_frag("Appendix B: Sources", 211.7, 28.0), _frag("130", 79.4, 28.6, x1=96.0)]
    count = first
    for k in range(16):
        y = 64.0 + 14.0 * k
        lines.append(_frag(f"line {k} of the Latin text, set in the edition's type", 140.9, y,
                           x1=416.3))
        if k % 5 == 3:
            lines.append(_frag(str(count), numbers_x0, y, x1=numbers_x0 + 9.5))
            count += step
    return SourcePage(index=140, width=496.0, height=700.0, lines=lines)


def test_the_line_count_in_the_margin_goes_and_the_folio_stays():
    rec = reconstruct(_edition_page(96.4))
    assert rec.line_numbers == 3
    assert not any(ln.startswith(("30 ", "35 ", "40 ")) for ln in rec.lines)
    assert "130" in rec.lines[0]


def test_a_count_on_the_recto_goes_as_well():
    rec = reconstruct(_edition_page(425.0))
    assert rec.line_numbers == 3
    assert not any(ln.endswith((" 30", " 35", " 40")) for ln in rec.lines)


def test_marginal_numbers_counting_by_one_stay():
    # A lawbook's marginal paragraph numbers are named in citations ("Rn. 10").
    rec = reconstruct(_edition_page(96.4, step=1, first=10))
    assert rec.line_numbers == 0
    assert any(ln.startswith("10 ") for ln in rec.lines)
