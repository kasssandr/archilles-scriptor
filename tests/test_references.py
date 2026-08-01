from scriptor.reflow.references import merge_reference_entries

BODY = 9.06
SMALL = 6.95


def _page(lines, sizes, indents=None):
    return lines, sizes, (indents if indents is not None else [55.0] * len(lines))


# Sen et al. p.8: the reference list is set at 6.9pt under a 10.9pt heading, and
# every entry hangs — the first line at the column edge, its continuations indented.
SEN_LINES = [
    "agents should reach for lexical compared to semantic search.",
    "References",
    "[1] Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, and Hannaneh Hajishirzi. 2024.",
    "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection.",
    "In Proceedings of ICLR.",
    "[2] Mark Chen, Jerry Tworek, Heewoo Jun, et al. 2021. Evaluating Large Language",
    "Models Trained on Code. arXiv preprint arXiv:2107.03374 (2021).",
]
SEN_SIZES = [BODY, 10.91, SMALL, SMALL, SMALL, SMALL, SMALL]
SEN_INDENTS = [55.0, 55.0, 55.0, 65.0, 65.0, 55.0, 65.0]


def test_a_hanging_reference_entry_becomes_one_line():
    pages = [_page(SEN_LINES, SEN_SIZES, SEN_INDENTS)]

    (lines, sizes, indents), = merge_reference_entries(pages, body_size=BODY)

    # The blank line before each entry is the paragraph seam parse_page already
    # reads; without it the whole list arrives as one paragraph.
    assert lines == [
        "agents should reach for lexical compared to semantic search.",
        "References",
        "",
        "[1] Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, and Hannaneh Hajishirzi. "
        "2024. Self-RAG: Learning to Retrieve, Generate, and Critique through "
        "Self-Reflection. In Proceedings of ICLR.",
        "",
        "[2] Mark Chen, Jerry Tworek, Heewoo Jun, et al. 2021. Evaluating Large "
        "Language Models Trained on Code. arXiv preprint arXiv:2107.03374 (2021).",
    ]
    assert len(sizes) == len(lines) == len(indents)


def test_a_merged_entry_carries_no_indent():
    """An entry is no longer a printed line, so the indent logic must not read a
    paragraph break out of its hanging continuation."""
    pages = [_page(SEN_LINES, SEN_SIZES, SEN_INDENTS)]

    (_lines, _sizes, indents), = merge_reference_entries(pages, body_size=BODY)

    assert indents[-2:] == [None, None]


def test_a_word_broken_across_two_lines_is_rejoined():
    lines = ["References", "[1] Vladimir Karpukhin. 2020. Dense Passage Retrieval for Open-",
             "Domain Question Answering. In Proceedings of EMNLP."]
    pages = [_page(lines, [10.91, SMALL, SMALL])]

    (out, _s, _i), = merge_reference_entries(pages, body_size=BODY)

    assert out[1] == ""
    assert out[2] == (
        "[1] Vladimir Karpukhin. 2020. Dense Passage Retrieval for OpenDomain "
        "Question Answering. In Proceedings of EMNLP."
    )


def test_the_block_ends_where_the_type_grows_again():
    """Sen et al. p.9: the appendix follows the references, set at body size."""
    lines = ["References", "[1] Akari Asai. 2024. Self-RAG.", "continued line of that entry",
             "A Per-Category Accuracy", "Table 4 reports accuracy by category."]
    sizes = [10.91, SMALL, SMALL, BODY, BODY]
    pages = [_page(lines, sizes)]

    (out, _s, _i), = merge_reference_entries(pages, body_size=BODY)

    assert out == [
        "References",
        "",
        "[1] Akari Asai. 2024. Self-RAG. continued line of that entry",
        "A Per-Category Accuracy",
        "Table 4 reports accuracy by category.",
    ]


def test_the_block_runs_across_a_page_break():
    first = _page(["References", "[1] Akari Asai. 2024. Self-RAG.", "In Proceedings of ICLR."],
                  [10.91, SMALL, SMALL])
    second = _page(["[2] Mark Chen. 2021. Evaluating Large Language", "Models Trained on Code."],
                   [SMALL, SMALL])

    (one, _s1, _i1), (two, _s2, _i2) = merge_reference_entries([first, second], body_size=BODY)

    assert one == ["References", "",
                   "[1] Akari Asai. 2024. Self-RAG. In Proceedings of ICLR."]
    assert two == ["", "[2] Mark Chen. 2021. Evaluating Large Language Models Trained on Code."]


def test_a_running_head_inside_the_block_neither_ends_it_nor_joins_an_entry():
    """A bibliography running over three pages prints the running head on each.

    It is set at body size, so by type alone it looks like the end of the list —
    but the list continues under it. And it must stay a line of its own, or the
    running-element stripper (which runs later) can no longer remove it and
    "Sen et al." ends up inside a citation.
    """
    first = _page(["References", "[1] Akari Asai. 2024. Self-RAG.", "In Proceedings of ICLR."],
                  [10.91, SMALL, SMALL])
    second = _page(["Sen et al.", "continued line of entry one",
                    "[2] Mark Chen. 2021. Evaluating Large Language Models."],
                   [BODY, SMALL, SMALL])

    (one, _s1, _i1), (two, _s2, _i2) = merge_reference_entries([first, second], body_size=BODY)

    assert one == ["References", "",
                   "[1] Akari Asai. 2024. Self-RAG. In Proceedings of ICLR. "
                   "continued line of entry one"]
    assert two == ["Sen et al.", "",
                   "[2] Mark Chen. 2021. Evaluating Large Language Models."]


def test_the_word_references_in_running_prose_opens_nothing():
    """Without numbered entries under it, the word is prose, not a section head."""
    lines = ["References", "to the earlier study are collected in the appendix.",
             "The argument continues here for another line or so."]
    pages = [_page(lines, [BODY, BODY, BODY])]

    (out, _s, _i), = merge_reference_entries(pages, body_size=BODY)

    assert out == lines


def test_a_document_without_a_reference_list_is_untouched():
    lines = ["Die erste Zeile eines Absatzes.", "und ihre Fortsetzung."]
    pages = [_page(lines, [BODY, BODY])]

    (out, sizes, indents), = merge_reference_entries(pages, body_size=BODY)

    assert out == lines
    assert sizes == [BODY, BODY]
    assert indents == [55.0, 55.0]
