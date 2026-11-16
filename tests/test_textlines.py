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


def test_a_line_set_across_the_page_is_read_ahead_of_it():
    """arXiv stamps its preprints down the left margin: 'arXiv:2605.15184v1
    [cs.CL] 14 May 2026' in a box 27pt wide and 353pt tall.

    Its baseline puts it in the middle of the first paragraph, where it breaks a
    sentence in half. It is not deleted — it says where the paper came from — but
    it is read ahead of the page, not inside it. Ahead, because the foot of the
    page carries the printed page number, and that number is the citation.
    """
    page = SourcePage(
        index=1,
        width=612.0,
        lines=[
            _frag("Modern LLM agents increasingly rely on RAG", 55.0, 300.0),
            Line(
                spans=[Span("arXiv:2605.15184v1 [cs.CL] 14 May 2026",
                            box=Box(10.9, 219.3, 37.6, 572.6), size=9.0)],
                box=Box(10.9, 219.3, 37.6, 572.6),
                baseline=250.0,
            ),
            _frag("to access external knowledge at inference time", 55.0, 312.0),
        ],
    )

    result = reconstruct(page)

    assert result.lines == [
        "arXiv:2605.15184v1 [cs.CL] 14 May 2026",
        "Modern LLM agents increasingly rely on RAG",
        "to access external knowledge at inference time",
    ]


def test_a_slightly_tall_scrap_is_not_a_margin_stamp():
    """Zuckerman p.399 carries an OCR scrap at the edge, '•־־׳־ 399', whose box is
    a little taller than wide. Treated as a stamp it survives into the text, where
    the page-label detection had been quietly dropping it.

    A stamp runs down the whole margin: it is *much* taller than it is wide.
    """
    box = Box(20.0, 700.0, 44.0, 730.0)          # 24pt wide, 30pt tall
    page = SourcePage(
        index=1,
        width=332.0,
        lines=[
            _frag("prose line of the page", 30.0, 100.0),
            Line(spans=[Span("•־־׳־ 399", box=box, size=9.0)], box=box, baseline=725.0),
        ],
    )

    result = reconstruct(page)

    assert result.lines[-1] == "•־־׳־ 399"


# --- a folio in the margin beside the last line of text ---------------------
# Fried, *Karl der Große* (Beck 2013): the page number stands in the outer
# margin on the baseline of the last line of text, the running title below.

def _body(text, x0, baseline, x1=330.0, size=10.0):
    box = Box(x0, baseline - 8.0, x1, baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def _fried_page(folio_x0, folio, body_x0, title_x0):
    return SourcePage(index=35, width=394.0, height=618.0, lines=[
        _body(folio, folio_x0, 537.8, x1=folio_x0 + 10, size=9.0),
        _body("Die unbekannte Kindheit eines Herrschers", title_x0, 566.0,
              x1=366.0, size=8.0),
        _body("Kleinkindes oblag, noch in Karls ersten Königsjahren einigen Ein-",
              body_x0, 510.1),
        _body("ﬂuß auf den Sohn und unter den Franken, bevor Karl sich ihm ent-",
              body_x0, 523.9),
        _body("zog. Bertrada entstammte einer der mächtigsten Familien Austra-",
              body_x0, 537.8),
    ])


def test_a_folio_beside_the_last_line_on_a_recto_is_a_line_of_its_own():
    result = reconstruct(_fried_page(356.0, "35", 46.0, 221.0))
    assert result.lines[-3:] == [
        "zog. Bertrada entstammte einer der mächtigsten Familien Austra-",
        "Die unbekannte Kindheit eines Herrschers",
        "35",
    ]


def test_a_folio_beside_the_last_line_on_a_verso_is_a_line_of_its_own():
    # Read along, "Rom-" / "36 gründer" had become "Rom36 gründer".
    result = reconstruct(_fried_page(29.0, "36", 66.0, 29.0))
    assert result.lines[-3] == (
        "zog. Bertrada entstammte einer der mächtigsten Familien Austra-")
    assert result.lines[-1] == "36"


def test_a_number_inside_the_type_area_stays_on_its_line():
    # A contents entry or a table's last cell ends at the measure, not past it.
    page = SourcePage(index=5, width=394.0, height=618.0, lines=[
        _body("Vorwort", 46.0, 100.0, x1=90.0),
        _body("9", 320.0, 100.0, x1=330.0),
        _body("Der Knabe und seine Welt, ein langer Titel der Zeile", 46.0, 114.0),
    ])
    result = reconstruct(page)
    assert result.lines == ["Vorwort 9", "Der Knabe und seine Welt, ein langer Titel der Zeile"]


def test_a_marginal_number_beside_another_line_is_not_taken():
    # A paragraph number in the margin beside the first line counts the text.
    page = SourcePage(index=5, width=394.0, height=618.0, lines=[
        _body("12", 340.0, 100.0, x1=350.0),
        _body("Erste Zeile des Absatzes mit seiner Randnummer daneben", 46.0, 100.0),
        _body("Zweite Zeile des Absatzes, die ohne jede Nummer auskommt", 46.0, 114.0),
    ])
    result = reconstruct(page)
    assert result.lines[0] == "Erste Zeile des Absatzes mit seiner Randnummer daneben 12"
