from scriptor.reflow.tables import BREAK, fold_tables

# Sen et al. p.7, Table 2: seven columns on a stable grid, model names left
# implicit on the second row of each pair.
SEN_ROWS = [
    [(78.0, "Table 2: Experiment 2 (grep-only): overall accuracy (%)")],
    [(188.0, "Model"), (268.0, "Harness"), (322.0, "s5"), (343.0, "s10"),
     (366.0, "s20"), (389.0, "s30"), (412.0, "full")],
    [(188.0, "Claude Opus 4.6"), (268.0, "Chronos"), (319.0, "89.3"), (342.0, "89.7"),
     (365.0, "90.5"), (388.0, "85.3"), (411.0, "89.7")],
    [(268.0, "Claude Code"), (319.0, "91.4"), (342.0, "94.0"),
     (365.0, "95.7"), (388.0, "90.5"), (411.0, "94.0")],
    [(188.0, "Claude Haiku 4.5"), (268.0, "Chronos"), (319.0, "83.7"), (342.0, "84.5"),
     (365.0, "86.2"), (388.0, "85.3"), (411.0, "83.6")],
    [(78.0, "bookkeeping. We state this as a hypothesis: our tables do not")],
]


def _texts(rows):
    return [" ".join(t for _x, t in row) for row in rows]


def _fold(rows):
    lines = _texts(rows)
    n = len(lines)
    return fold_tables(rows, lines, [9.0] * n, [55.0] * n, [0] * n)


def _table_of(rows):
    """The one folded table in the result."""
    return next(ln for ln in _fold(rows)[0] if ln.startswith("|"))


def test_a_grid_of_cells_becomes_a_markdown_table():
    lines, sizes, indents, emphases = _fold(SEN_ROWS)

    assert lines[0] == SEN_ROWS[0][0][1]          # the caption stays prose
    table = _table_of(SEN_ROWS)
    assert table.startswith("| Model | Harness | s5 | s10 | s20 | s30 | full |")
    assert f"{BREAK}| --- | --- | --- | --- | --- | --- | --- |{BREAK}" in table
    assert "| Claude Opus 4.6 | Chronos | 89.3 | 89.7 | 90.5 | 85.3 | 89.7 |" in table
    assert lines[-1] == SEN_ROWS[-1][0][1]        # the prose after it stays prose
    assert len(lines) == len(sizes) == len(indents) == len(emphases)


def test_a_cell_the_row_leaves_empty_stays_empty():
    """Table 2 prints the model name once for its two harness rows."""
    assert "|  | Claude Code | 91.4 |" in _table_of(SEN_ROWS)


def test_prose_lines_that_arrive_in_fragments_are_not_a_table():
    """Seeck hands over 731 fragments for 216 printed lines. Their left edges
    scatter, which is what tells a broken line from a set column."""
    rows = [
        [(30.0, "Herren,"), (85.0, "falls"), (108.0, "sie"), (125.0, "sich dieses")],
        [(30.0, "Verbrechens"), (99.0, "schuldig"), (140.0, "gemacht"), (190.0, "haben")],
        [(30.0, "sollten,"), (72.0, "so"), (95.0, "wird der Kaiser"), (170.0, "sie")],
        [(30.0, "nicht"), (60.0, "schonen"), (110.0, "und"), (140.0, "auch nicht")],
    ]

    lines, _s, _i, _e = _fold(rows)

    assert lines == _texts(rows)


def test_two_rows_are_not_a_table():
    rows = [
        [(188.0, "Model"), (268.0, "Harness"), (322.0, "s5")],
        [(188.0, "Claude Opus"), (268.0, "Chronos"), (319.0, "89.3")],
    ]

    lines, _s, _i, _e = _fold(rows)

    assert lines == _texts(rows)


def test_a_pipe_inside_a_cell_is_escaped():
    rows = [
        [(188.0, "a|b"), (268.0, "c"), (322.0, "d")],
        [(188.0, "e"), (268.0, "f"), (322.0, "g")],
        [(188.0, "h"), (268.0, "i"), (322.0, "j")],
    ]

    assert "a\\|b" in _table_of(rows)


# --- tables that span the gutter of a two-column page --------------------------

from scriptor.reflow.columns import Gutter
from scriptor.reflow.tables import spanning_rows


def test_a_table_across_the_gutter_is_found_as_one_block():
    """Sen et al. Table 2 runs the full measure of a two-column page: its cells
    sit at 188 and 268 (left of the lane) and at 319..411 (right of it).

    Cell by cell the column rule would send half the row into the left column and
    half into the right, and the table would arrive as two heaps of fragments.
    """
    rows = [
        [(78.0, "bookkeeping. We state this as a hypothesis: our tables")],
        [(188.0, "Model"), (268.0, "Harness"), (322.0, "s5"), (343.0, "s10"),
         (366.0, "s20"), (389.0, "s30"), (412.0, "full")],
        [(188.0, "Claude Opus 4.6"), (268.0, "Chronos"), (319.0, "89.3"),
         (342.0, "89.7"), (365.0, "90.5"), (388.0, "85.3"), (411.0, "89.7")],
        [(268.0, "Claude Code"), (319.0, "91.4"), (342.0, "94.0"),
         (365.0, "95.7"), (388.0, "90.5"), (411.0, "94.0")],
        [(188.0, "Claude Haiku 4.5"), (268.0, "Chronos"), (319.0, "83.7"),
         (342.0, "84.5"), (365.0, "86.2"), (388.0, "85.3"), (411.0, "83.6")],
    ]

    assert spanning_rows(rows, Gutter(295.4, 317.9)) == {1, 2, 3, 4}


def test_two_columns_of_prose_are_not_a_spanning_table():
    """Every printed line of a two-column page has material on both sides of the
    lane — that is what a shared baseline grid means, and it is not a table."""
    rows = [
        [(55.0, "the left column line of prose"), (320.0, "the right column line")],
        [(55.0, "another left column line"), (320.0, "another right column line")],
        [(55.0, "a third left column line"), (320.0, "a third right column line")],
        [(55.0, "a fourth left column line"), (320.0, "a fourth right column")],
    ]

    assert spanning_rows(rows, Gutter(295.4, 317.9)) == set()


def test_a_folded_table_stands_on_its_own():
    """A table has to be a paragraph of its own: glued to its caption or to the
    prose below it, Markdown reads neither as a table."""
    rows = [
        [(78.0, "Table 2: Experiment 2 (grep-only): overall accuracy")],
        [(188.0, "Model"), (268.0, "Harness"), (322.0, "s5")],
        [(188.0, "Claude Opus"), (268.0, "Chronos"), (319.0, "89.3")],
        [(188.0, "Claude Haiku"), (268.0, "Chronos"), (319.0, "83.7")],
        [(78.0, "bookkeeping. We state this as a hypothesis: our tables")],
    ]

    lines, sizes, indents, emphases = _fold(rows)

    assert lines[1] == ""
    assert lines[2].startswith("| Model |")
    assert lines[3] == ""
    assert lines[4].startswith("bookkeeping")
    assert len(lines) == len(sizes) == len(indents) == len(emphases)
