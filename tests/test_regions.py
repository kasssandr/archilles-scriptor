from scriptor.reflow.core import detect_page_number, parse_page, reconcile_page_numbers, Page


def test_pure_digit_line_is_page_number():
    assert detect_page_number("146") == 146
    assert detect_page_number("  23 ") == 23


def test_number_with_allcaps_running_head():
    # Braunfels: page number sits at the start of a running-head line.
    assert detect_page_number("146 WILHELM HEIL") == 146
    assert detect_page_number("L'ORIGINE DE LA NOBLESSE 23") == 23


def test_body_number_is_not_a_page_number():
    # Leading year in ordinary prose must NOT be taken as a page number
    # (the trailing text is not running-head-like).
    assert detect_page_number("1990 war ein gutes Jahr fuer die Forschung") is None
    assert detect_page_number("3. Die Probleme um Welf VI. im Vergleich") is None


def test_non_numeric_line_is_none():
    assert detect_page_number("Ein ganz normaler Satz.") is None
    assert detect_page_number("") is None


def test_implausible_number_is_none():
    # 5-digit / zero are not plausible book page numbers.
    assert detect_page_number("12345") is None
    assert detect_page_number("0") is None


def test_parse_page_records_bottom_number():
    pg = parse_page("Ein Absatz Text hier.\n146")
    assert pg.num_bottom == 146 and pg.num_top == -1


def test_parse_page_records_top_number_with_head():
    pg = parse_page("146 WILHELM HEIL\nKommentare hinaus, war doch die Bibel.")
    assert pg.num_top == 146
    # the running-head line is stripped from the body
    assert not any("WILHELM HEIL" in ln for ln in pg.body_lines)


def test_reconcile_picks_bottom_sequence():
    pages = [Page(-1, ["a"], {}), Page(-1, ["b"], {}), Page(-1, ["c"], {})]
    pages[0].num_bottom, pages[1].num_bottom, pages[2].num_bottom = 10, 11, 12
    pages[0].num_top, pages[1].num_top, pages[2].num_top = 99, 3, 50  # noise
    col = reconcile_page_numbers(pages)
    assert col == "bottom"
    assert [p.num for p in pages] == [10, 11, 12]


def test_reconcile_picks_top_sequence():
    pages = [Page(-1, ["a"], {}), Page(-1, ["b"], {}), Page(-1, ["c"], {})]
    pages[0].num_top, pages[1].num_top, pages[2].num_top = 5, 6, 7
    col = reconcile_page_numbers(pages)
    assert col == "top"
    assert [p.num for p in pages] == [5, 6, 7]


def test_reconcile_no_signal_leaves_minus_one():
    pages = [Page(-1, ["a"], {}), Page(-1, ["b"], {})]
    col = reconcile_page_numbers(pages)
    assert col == "none"
    assert [p.num for p in pages] == [-1, -1]
