from scriptor.page import Box, Line, SourcePage, Span
from scriptor.reflow.textlines import reconstruct


def _frag(text, x0, baseline, *, x1=None, top=None):
    """A line fragment. ``top`` defaults just above the baseline."""
    x1 = x1 if x1 is not None else x0 + 6 * len(text)
    top = top if top is not None else baseline - 7.0
    box = Box(x0, top, x1, baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=9.0)], box=box, baseline=baseline)


def test_fragments_on_one_baseline_become_one_printed_line():
    """Thil-Lorrain p.136: four fragments, one printed line, x order decides."""
    page = SourcePage(
        index=1,
        width=312.0,
        lines=[
            _frag("I. Et", 40, 63.0),
            _frag("d'abord , comment supposer", 69, 63.0),
            _frag("qu'un", 200, 63.0),
            _frag("prélat", 230, 63.4),
            _frag("comme saint Lambert ait été assez", 30, 75.5),
        ],
    )

    result = reconstruct(page)

    assert result.measured is True
    assert result.lines == [
        "I. Et d'abord , comment supposer qu'un prélat",
        "comme saint Lambert ait été assez",
    ]


def test_clustering_uses_the_baseline_not_the_box_top():
    """Seeck p.120: within one printed line the box top scatters by 2.2pt.

    'falls' sits 2.2pt below 'sich' because it has no ascender. Clustering on the
    box would tear it out of its line and print it on its own.
    """
    page = SourcePage(
        index=1,
        width=346.0,
        lines=[
            _frag("Herren,", 25.5, 98.34, top=91.08),
            _frag("falls", 84.9, 98.34, top=92.97),
            _frag("sie", 108.3, 98.34, top=92.84),
            _frag("sich dieses Verbrechens schuldig", 124.6, 98.34, top=90.77),
        ],
    )

    result = reconstruct(page)

    assert result.lines == ["Herren, falls sie sich dieses Verbrechens schuldig"]


def test_a_tolerance_is_needed_the_baselines_are_not_identical():
    """Seeck: 98.34 and 98.70 belong together; a bare equality check splits them."""
    page = SourcePage(
        index=1, width=346.0,
        lines=[_frag("ihre", 25.5, 98.70), _frag("Herren,", 60.0, 98.34)],
    )

    assert reconstruct(page).lines == ["ihre Herren,"]
    assert len(reconstruct(page, tolerance=0.0).lines) == 2


def test_a_tolerance_of_two_would_merge_two_printed_lines():
    """Seeck's printed lines sit ~12.5pt apart, but footnote lines sit closer.

    Two points is too generous: it is why BASELINE_TOLERANCE is 1.0.
    """
    page = SourcePage(
        index=1, width=346.0,
        lines=[_frag("erste Zeile", 25.5, 100.0), _frag("zweite Zeile", 25.5, 101.8)],
    )

    assert len(reconstruct(page).lines) == 2
    assert len(reconstruct(page, tolerance=2.0).lines) == 1


def test_already_whole_lines_are_left_alone():
    page = SourcePage(
        index=1,
        width=331.0,
        lines=[_frag("documents of the same Viennois region", 30, 43.0),
               _frag("references to terrae of individual Jews", 30, 52.8)],
    )

    assert reconstruct(page).lines == [
        "documents of the same Viennois region",
        "references to terrae of individual Jews",
    ]


def test_a_wide_gap_inside_the_page_is_counted():
    page = SourcePage(
        index=1,
        width=400.0,
        lines=[
            _frag("erste Zeile", 20, 50.0),
            _frag("left column", 20, 100.0, x1=150),
            _frag("right column", 320, 100.0, x1=380),
            _frag("letzte Zeile", 20, 150.0),
        ],
    )

    result = reconstruct(page)

    assert result.wide_gap_lines == 1


def test_a_running_head_and_its_page_number_do_not_warn():
    """Zuckerman p.212: 84pt of white between title and folio, at 332pt width.

    That is 25.3 % — a column break it is not. The topmost and bottommost printed
    lines are exempt, because that is where running heads and folios live.
    """
    page = SourcePage(
        index=1,
        width=332.0,
        lines=[
            _frag("The First Generations of the Jewish Principate", 30, 25.0, x1=225),
            _frag("193", 309, 25.0, x1=325),
            _frag("body text of the page", 30, 60.0),
            _frag("folio", 30, 500.0, x1=60),
            _frag("299", 300, 500.0, x1=320),
        ],
    )

    result = reconstruct(page)

    assert result.lines[0] == "The First Generations of the Jewish Principate 193"
    assert result.wide_gap_lines == 0


def test_pages_without_geometry_are_passed_through_unchanged():
    page = SourcePage(
        index=1,
        lines=[Line(spans=[Span("alpha")]), Line(spans=[]), Line(spans=[Span("beta")])],
    )

    result = reconstruct(page)

    assert result.measured is False
    assert result.lines == ["alpha", "", "beta"]
    assert result.wide_gap_lines == 0


def test_a_half_measured_page_is_not_reordered():
    """One line without a baseline and we measure nothing: sorting the rest would
    move the unmeasured line to an arbitrary place."""
    page = SourcePage(
        index=1, width=300.0,
        lines=[_frag("gemessen", 20, 50.0), Line(spans=[Span("ungemessen")])],
    )

    result = reconstruct(page)

    assert result.measured is False
    assert result.lines == ["gemessen", "ungemessen"]


def test_an_empty_page_reconstructs_to_nothing():
    result = reconstruct(SourcePage(index=1))
    assert result.lines == []
    assert result.measured is False


def _styled(parts, x0, baseline):
    """A printed line from (text, bold, italic) parts, laid out left to right."""
    spans, x = [], x0
    for text, bold, italic in parts:
        width = 6 * len(text)
        spans.append(Span(text, box=Box(x, baseline - 7.0, x + width, baseline + 2.0),
                          size=9.0, bold=bold, italic=italic))
        x += width
    box = Box(x0, baseline - 7.0, x, baseline + 2.0)
    return Line(spans=spans, box=box, baseline=baseline)


def test_the_emphasised_head_of_a_line_is_measured():
    """Sen et al. p.3 sets a run-in heading in italics and the prose that follows
    in roman, on one printed line: '3.2.1 Lexical Search (Grep). The grep tool …'
    """
    page = SourcePage(
        index=1,
        width=612.0,
        lines=[
            _styled([("3.2.1 Lexical Search (Grep).", False, True),
                     (" The grep retrieval tool loads", False, False)], 55.0, 90.0),
            _styled([("2.3 Tool-Calling Architectures", True, False)], 55.0, 110.0),
            _styled([("Orthogonal to the choice of harness", False, False)], 55.0, 130.0),
        ],
    )

    result = reconstruct(page)

    assert result.emphases == [28, 30, 0]
    assert result.lines[0] == "3.2.1 Lexical Search (Grep). The grep retrieval tool loads"


def test_emphasis_across_two_fragments_counts_the_joining_space():
    """Sen et al. hands over the number and the title as separate fragments:
    '2.3' and 'Tool-Calling Architectures'. Assembly puts a space between them,
    and the emphasis run has to cover it, or the heading loses its last letter."""
    page = SourcePage(
        index=1,
        width=612.0,
        lines=[
            _styled([("2.3", True, False)], 55.0, 90.0),
            _styled([("Tool-Calling Architectures", True, False)], 75.0, 90.0),
        ],
    )

    result = reconstruct(page)

    assert result.lines == ["2.3 Tool-Calling Architectures"]
    assert result.emphases == [len("2.3 Tool-Calling Architectures")]
