from scriptor.reflow.core import heading_level


def test_a_numbered_section_is_a_heading():
    """Hechberger: '3.4. Probleme um Welf VI.' — number, period, title."""
    assert heading_level("3.4. Probleme um Welf VI.") == 2
    assert heading_level("4. Ergebnisse") == 1


def test_a_year_opening_a_paragraph_is_not_a_heading():
    """Sen et al., reference [4]: the entry continues '… Clinchant. 2021. SPLADE
    v2: Sparse Lexical and Expansion Model …' and the year opens a paragraph.

    Section numbers count chapters, not years: a document with 2021 sections does
    not exist, and rendering a bibliography line as '# 2021. SPLADE v2' both
    invents structure and hides the reference from anyone reading the headings.
    """
    assert heading_level("2021. SPLADE v2: Sparse Lexical and Expansion Model.") == 0
    assert heading_level("1949. Die Entstehung des Deutschen Reiches.") == 0


def test_a_long_line_is_prose_however_it_starts():
    assert heading_level("3. " + "Wort " * 30) == 0
