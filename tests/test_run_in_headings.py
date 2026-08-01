from scriptor.reflow.core import heading_level
from scriptor.reflow.headings import MARK, split_emphasised_headings


def test_a_numbered_section_without_a_period_is_a_heading():
    """ACM numbers without a period: '2.1 Retrieval Strategies'. Hechberger's
    '3.4. Probleme um Welf VI.' keeps working."""
    assert heading_level("2.1 Retrieval Strategies") == 2
    assert heading_level("3.4. Probleme um Welf VI.") == 2
    assert heading_level("4.1.2 Experimental setup.") == 3


def test_a_folio_before_a_running_head_is_not_a_heading():
    """Zuckerman prints '44 The Surrender of Narbonne' at the head of the page.

    A section number carries its subsection: without one, a bare number in front
    of a title is a folio, and reading it as a chapter would cut the page in two.
    """
    assert heading_level("44 The Surrender of Narbonne") == 0
    assert heading_level("193 The First Generations of the Jewish Principate") == 0


def test_a_run_in_heading_is_cut_off_its_paragraph():
    """Sen et al. p.3: the heading is italic, the prose of the same printed line
    is roman. Cutting at the emphasis makes the heading a line of its own."""
    lines = ["3.2.1 Lexical Search (Grep). The grep retrieval tool loads conversation"]
    emphases = [28]

    out = split_emphasised_headings(lines, emphases, [None], [55.0])

    assert out[0] == [
        MARK + "3.2.1 Lexical Search (Grep).",
        "The grep retrieval tool loads conversation",
    ]
    assert out[1] == [None, None]      # sizes stay parallel
    assert out[2] == [55.0, None]      # the cut-off remainder has no printed edge


def test_a_fully_emphasised_heading_line_is_marked_but_not_cut():
    lines = ["2.3 Tool-Calling Architectures", "Orthogonal to the choice of harness"]

    out = split_emphasised_headings(lines, [30, 0], [None, None], [55.0, 55.0])

    assert out[0] == [MARK + "2.3 Tool-Calling Architectures",
                      "Orthogonal to the choice of harness"]


def test_an_italic_title_inside_a_sentence_cuts_nothing():
    """Emphasis alone is not a heading: without a section number in front, an
    italic work title at the start of a line is just a title."""
    lines = ["Römische Geschichte, so Mommsen, sei kein Handbuch der Feldzüge"]

    out = split_emphasised_headings(lines, [18], [None], [55.0])

    assert out[0] == lines


def test_an_unemphasised_line_is_never_cut():
    lines = ["3.2.1 Lexical Search (Grep). The grep retrieval tool loads conversation"]

    out = split_emphasised_headings(lines, [0], [None], [55.0])

    assert out[0] == lines


def test_a_fully_emphasised_single_number_heading_is_marked():
    """'3 Methodology' is a chapter; '44 The Surrender of Narbonne' is a folio and
    a running head. Only the type tells them apart, so the type is carried over:
    a marked line is a heading, an unmarked one has to prove itself by numbering.
    """
    lines = ["3 Methodology", "44 The Surrender of Narbonne"]

    out = split_emphasised_headings(lines, [13, 0], [None, None], [55.0, 55.0])

    assert out[0] == [MARK + "3 Methodology", "44 The Surrender of Narbonne"]
    assert heading_level(out[0][0].lstrip(MARK), marked=True) == 1
    assert heading_level(out[0][1], marked=False) == 0


def test_the_mark_is_only_given_to_numbered_titles():
    """A fully italic line without a section number is a quotation or a caption."""
    lines = ["Römische Geschichte", "Abstract"]

    out = split_emphasised_headings(lines, [19, 8], [None, None], [55.0, 55.0])

    assert out[0] == lines


def test_an_emphasised_line_after_ordinary_prose_gets_no_mark():
    """Only a heading's own continuation inherits the mark, not any emphasis."""
    lines = ["Ein gewoehnlicher Absatz endet hier.", "Römische Geschichte"]

    out = split_emphasised_headings(lines, [0, 19], [None, None], [55.0, 55.0])

    assert out[0] == lines


def test_a_page_number_split_into_digits_is_not_a_heading():
    """Zuckerman's OCR layer hands over the folio as '2 0 8' and calls it italic.

    By the numbering rule alone that reads as section 2 with the title '0 8'. A
    title starts with a letter, so the digits give it away.
    """
    lines = ["2 0 8", "7 6", "1 2 0"]

    out = split_emphasised_headings(lines, [5, 3, 5], [None] * 3, [55.0] * 3)

    assert out[0] == lines


def test_a_german_ordinal_is_not_a_marked_heading():
    """'16. Jahrhundert' inside the prose of a scan whose italics are unreliable.

    A single number followed by a period is an ordinal in German; the marked path
    only accepts a subsection ('4.1 …') or a number without a period ('3 Methodology'),
    which is how scholarly articles set them.
    """
    lines = ["16. Jahrhundert"]

    out = split_emphasised_headings(lines, [15], [None], [55.0])

    assert heading_level(out[0][0].lstrip(MARK), marked=True) == 0
    assert heading_level("3 Methodology", marked=True) == 1
    assert heading_level("4.1 Experiment 1: Retrieval Mode", marked=True) == 2


def test_a_title_broken_before_an_ordinal_is_not_cut():
    """Zuckerman's bibliography breaks an italic title across two printed lines:
    '… Das Wesen der Monarchie vom 9. bis zum' / '16. Jahrhundert, 2 vols. Weimar
    1939.' The second line opens with what looks like a section number, and
    cutting there leaves 'Jahrhundert , 2 vols.' — a space before the comma.

    Same rule as for the mark: a subsection, or a number without a period.
    """
    lines = ["16. Jahrhundert, 2 vols. Weimar 1939. 2nd ed. rev. 1960."]

    out = split_emphasised_headings(lines, [17], [None], [55.0])

    assert out[0] == lines


def test_an_unnumbered_heading_is_recognised_by_its_type():
    """Sen et al. sets "Abstract", "Keywords", "References" and the appendix head
    "A Per-Category Accuracy" bold at 10.91pt over 9.06pt body — no number
    anywhere. Type alone carries them, so both grade and emphasis are required:
    an italic work title at body size stays a work title.
    """
    lines = ["Abstract", "References", "Römische Geschichte", "A Per-Category Accuracy"]
    sizes = [10.91, 10.91, 9.06, 10.91]
    emph = [len(lines[0]), len(lines[1]), len(lines[2]), len(lines[3])]

    out = split_emphasised_headings(lines, emph, sizes, [55.0] * 4, body_size=9.06)

    assert out[0] == [MARK + "Abstract", MARK + "References",
                      "Römische Geschichte", MARK + "A Per-Category Accuracy"]
    assert heading_level("Abstract", marked=True) == 1
    assert heading_level("A Per-Category Accuracy", marked=True) == 1


def test_a_heading_broken_over_two_lines_is_joined_where_it_is_cut():
    """The continuation carries no number of its own and is joined right here,
    so nothing downstream has to know that a heading can span two lines."""
    lines = ["4.1 Experiment 1: Retrieval Mode, Harness, and", "Tool Calling Method",
             "Wir isolieren zunaechst den Einfluss des Modus."]

    out = split_emphasised_headings(
        lines, [len(lines[0]), len(lines[1]), 0], [None] * 3, [55.0] * 3
    )

    assert out[0] == [MARK + "4.1 Experiment 1: Retrieval Mode, Harness, and "
                             "Tool Calling Method",
                      "Wir isolieren zunaechst den Einfluss des Modus."]
