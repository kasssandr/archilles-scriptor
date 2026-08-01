"""Tables: the cells the reflow would otherwise pour into one sentence.

A results table is the argument of an empirical paper, and line assembly turns it
into a queue of numbers. Sen et al. Table 2 leaves the reflow as

    Model Harness s5 s10 s20 s30 full Claude Opus 4.6 Chronos 89.3 89.7 90.5 …

where every number has lost the column it was measured in. No reader and no
retriever can put them back.

The page still knows. Cells sit on a grid: seven columns at x = 188, 268, 319,
342, 365, 388, 411, held over every row of the table. That grid is the evidence
-- not the white between two words, which scatters, and not the number of
fragments, which an OCR layer inflates at random. Three rows have to agree on a
grid of three columns before anything here fires, and a row whose cells do not
fit that grid ends the table rather than being forced into it.

A folded table is one "line" carrying ``BREAK`` where its rows divide, because
everything downstream reads a line as a paragraph. ``render_book`` turns the
breaks back into newlines at the very end, where every path meets.
"""

from __future__ import annotations

# Row separator inside a folded table. From the Private Use Area, like the
# heading mark: no document can contain it, and nothing downstream splits on it.
BREAK = ""

# A table needs this many rows that agree on the grid. Two rows are a coincidence
# -- a line and its continuation, broken at the same word by the same margin.
MIN_ROWS = 3

# …and this many columns. Two columns are a hanging indent or a folio and its
# running head, both of which are somebody else's job.
MIN_COLUMNS = 3

# Points a cell may sit off its column and still belong to it. Set columns hold
# to within a point or two; the number is generous because a right-aligned figure
# starts where its digits allow ("89.3" against "100.0").
COLUMN_TOLERANCE = 9.0

# A cell is a value, not a sentence. Half the cells longer than this and the grid
# is prose that happens to line up.
MAX_CELL_CHARS = 40

# Share of the grid a table actually fills. This is what separates a table from
# prose that arrived in fragments: Sen's Table 2 fills 33 of 35 cells, while four
# lines of Seeck fill 16 of 40 — every fragment opening a column only it uses.
# An empty cell is normal (Table 2 prints the model name once per pair), a grid
# of mostly empty cells is not a grid.
MIN_DENSITY = 0.7

Row = list[tuple[float, str]]


def _grid(rows: list[Row]) -> list[float]:
    """The column edges these rows share, left to right."""
    edges: list[float] = []
    for row in rows:
        for x, _text in row:
            for i, edge in enumerate(edges):
                if abs(edge - x) <= COLUMN_TOLERANCE:
                    edges[i] = min(edge, x)
                    break
            else:
                edges.append(x)
    return sorted(edges)


def _fits(row: Row, grid: list[float]) -> list[str] | None:
    """The row's cells in grid order, or None if it does not sit on the grid."""
    cells = [""] * len(grid)
    for x, text in row:
        hits = [i for i, edge in enumerate(grid) if abs(edge - x) <= COLUMN_TOLERANCE]
        if not hits:
            return None
        i = min(hits, key=lambda i: abs(grid[i] - x))
        if cells[i]:
            return None                       # two cells in one column: not a grid
        cells[i] = text.strip()
    return cells


def _is_candidate(row: Row) -> bool:
    return len(row) >= MIN_COLUMNS


def _cells_are_values(cells: list[str]) -> bool:
    """Does this row read like table cells rather than like a sentence?

    Checked row by row, not over the table as a whole: on Sen's p.9 the appendix
    heading and the tail of a caption sit right under Table 4 and fit its grid by
    accident, and a single sentence averaged over ten rows of figures disappears.
    """
    filled = [c for c in cells if c]
    return bool(filled) and all(len(c) <= MAX_CELL_CHARS for c in filled)


def _density(table: list[list[str]]) -> float:
    filled = sum(1 for row in table for c in row if c)
    return filled / sum(len(row) for row in table)


def _find_tables(rows: list[Row]) -> list[tuple[int, int, list[float]]]:
    """Runs of rows that share a grid: (start, end, grid)."""
    found: list[tuple[int, int, list[float]]] = []
    i = 0
    while i < len(rows):
        if not _is_candidate(rows[i]):
            i += 1
            continue
        j = i + 1
        while j < len(rows) and _is_candidate(rows[j]):
            j += 1
        block = rows[i:j]
        while len(block) >= MIN_ROWS:
            grid = _grid(block)
            fitted = [_fits(row, grid) for row in block]
            cells = [f for f in fitted if f]
            if (
                len(grid) >= MIN_COLUMNS
                and all(f is not None for f in fitted)
                and all(_cells_are_values(row) for row in cells)
                and _density(cells) >= MIN_DENSITY
            ):
                found.append((i, i + len(block), grid))
                break
            block = block[:-1]                # the last row broke it; try without
        i = j
    return found


def spanning_rows(rows: list[Row], gutter) -> set[int]:
    """Indices of rows belonging to a table that runs across the column gutter.

    A full-measure table is invisible to the column rule, which sees each cell on
    its own and sends "Model" into the left column and "89.3" into the right. It
    is visible here, because the table's *grid* has columns on both sides of the
    lane while a two-column page has one grid per column.
    """
    found: set[int] = set()
    for start, end, grid in _find_tables(rows):
        left = [x for x in grid if x < gutter.x0]
        right = [x for x in grid if x > gutter.x1]
        if left and right:
            found.update(range(start, end))
    return found


def _render(rows: list[Row], grid: list[float]) -> str:
    body = [_fits(row, grid) or [] for row in rows]
    out = [[c.replace("|", "\\|") for c in cells] for cells in body]
    head, rest = out[0], out[1:]
    lines = ["| " + " | ".join(head) + " |",
             "| " + " | ".join("---" for _ in grid) + " |"]
    lines += ["| " + " | ".join(cells) + " |" for cells in rest]
    return BREAK.join(lines)


def fold_tables(
    rows: list[Row],
    lines: list[str],
    sizes: list[float | None],
    indents: list[float | None],
    emphases: list[int],
) -> tuple[list[str], list[float | None], list[float | None], list[int]]:
    """Replace each detected table with a single folded Markdown line."""
    tables = _find_tables(rows)
    if not tables:
        return list(lines), list(sizes), list(indents), list(emphases)

    out_lines: list[str] = []
    out_sizes: list[float | None] = []
    out_indents: list[float | None] = []
    out_emphases: list[int] = []

    starts = {start: (end, grid) for start, end, grid in tables}
    i = 0
    while i < len(lines):
        if i in starts:
            end, grid = starts[i]
            # Blank lines around it: the paragraph seam parse_page already reads.
            # Glued to its caption or to the prose below, Markdown reads neither
            # as a table.
            for text in ("", _render(rows[i:end], grid), ""):
                out_lines.append(text)
                out_sizes.append(sizes[i] if i < len(sizes) else None)
                # A table is not a printed line: no left edge, no emphasis to read.
                out_indents.append(None)
                out_emphases.append(0)
            i = end
            continue
        out_lines.append(lines[i])
        out_sizes.append(sizes[i] if i < len(sizes) else None)
        out_indents.append(indents[i] if i < len(indents) else None)
        out_emphases.append(emphases[i] if i < len(emphases) else 0)
        i += 1
    return out_lines, out_sizes, out_indents, out_emphases
