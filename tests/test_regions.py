from scriptor.reflow.core import detect_page_number, parse_page, reconcile_page_numbers, Page, estimate_body_width, is_prose_page, assign_modes


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


def _prose_page(width=70, n=12):
    return Page(-1, ["x" * width for _ in range(n)], {})


def test_estimate_body_width_finds_dominant():
    pages = [_prose_page(70, 20), _prose_page(40, 3)]
    assert estimate_body_width(pages) == 70


def test_is_prose_page_true_for_full_text():
    pages = [_prose_page(70, 20)]
    w = estimate_body_width(pages)
    assert is_prose_page(_prose_page(70, 12), w) is True


def test_is_prose_page_false_for_short_list():
    # A title page / short-line page is not prose.
    w = 70
    short = Page(-1, ["VII", "Mahnung zur Tugend", "Ein kurzes Kapitel"], {})
    assert is_prose_page(short, w) is False


def test_assign_modes_promotes_prose_without_page1():
    # Snell case: prose pages, but no page numbered 1 -> still becomes main.
    pages = [_prose_page(70, 15) for _ in range(3)]
    for p in pages:
        p.num = 200  # no page == 1 anywhere
    assign_modes(pages)
    assert all(p.mode == "main" for p in pages)


def test_assign_modes_keeps_page1_fallback():
    # Frontmatter then a num==1 page that is NOT prose-dense still flips to main.
    fm = Page(-1, ["Titelei", "Verlag"], {})
    p1 = Page(1, ["Kurzer Anfang."], {})
    assign_modes([fm, p1])
    assert p1.mode == "main"
