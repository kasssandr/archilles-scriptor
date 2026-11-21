from scriptor.reflow.core import parse_page, reconcile_page_numbers, Page, estimate_body_width, is_prose_page, assign_modes, calibrate_threshold, CALIB_FALLBACK_MIN
from scriptor.reflow.pagelabel import detect_page_label


def test_pure_digit_line_is_page_label():
    assert detect_page_label("146") == "146"
    assert detect_page_label("  23 ") == "23"


def test_number_with_allcaps_running_head():
    # Braunfels: page number sits at the start of a running-head line.
    assert detect_page_label("146 WILHELM HEIL") == "146"
    assert detect_page_label("L'ORIGINE DE LA NOBLESSE 23") == "23"


def test_body_number_is_not_a_page_label():
    # Leading year in ordinary prose must NOT be taken as a page number
    # (the trailing text is not running-head-like).
    assert detect_page_label("1990 war ein gutes Jahr fuer die Forschung") is None
    assert detect_page_label("3. Die Probleme um Welf VI. im Vergleich") is None


def test_non_numeric_line_is_none():
    assert detect_page_label("Ein ganz normaler Satz.") is None
    assert detect_page_label("") is None


def test_implausible_number_is_none():
    # 5-digit / zero are not plausible book page numbers.
    assert detect_page_label("12345") is None
    assert detect_page_label("0") is None


def test_parse_page_records_bottom_label():
    pg = parse_page("Ein Absatz Text hier.\n146")
    assert pg.label_bottom == "146" and pg.label_top is None


def test_parse_page_records_top_label_with_head():
    pg = parse_page("146 WILHELM HEIL\nKommentare hinaus, war doch die Bibel.")
    assert pg.label_top == "146"
    # the running-head line is stripped from the body
    assert not any("WILHELM HEIL" in ln for ln in pg.body_lines)


def test_parse_page_single_line_is_bottom_only():
    pg = parse_page("146")
    assert pg.label_bottom == "146" and pg.label_top is None


def test_reconcile_picks_bottom_sequence():
    pages = [Page(-1, ["a"], {}), Page(-1, ["b"], {}), Page(-1, ["c"], {})]
    pages[0].label_bottom, pages[1].label_bottom, pages[2].label_bottom = "10", "11", "12"
    pages[0].label_top, pages[1].label_top, pages[2].label_top = "99", "3", "50"  # noise
    col = reconcile_page_numbers(pages)
    assert col == "bottom"
    assert [p.num for p in pages] == [10, 11, 12]


def test_reconcile_picks_top_sequence():
    pages = [Page(-1, ["a"], {}), Page(-1, ["b"], {}), Page(-1, ["c"], {})]
    pages[0].label_top, pages[1].label_top, pages[2].label_top = "5", "6", "7"
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


def test_estimate_body_width_empty_corpus():
    assert estimate_body_width([]) == 0


def test_is_prose_page_true_for_full_text():
    pages = [_prose_page(70, 20)]
    w = estimate_body_width(pages)
    assert is_prose_page(_prose_page(70, 12), w) is True


def test_is_prose_page_false_for_short_list():
    # A title page / short-line page is not prose.
    w = 70
    short = Page(-1, ["VII", "Mahnung zur Tugend", "Ein kurzes Kapitel"], {})
    assert is_prose_page(short, w) is False


def test_is_prose_page_false_for_zero_width():
    assert is_prose_page(_prose_page(70, 12), 0) is False


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


def _list_page(n=20):
    return Page(-1, [f"AUTOR, A., Titel {k}, Ort 19{k:02d}" for k in range(n)], {})


def test_bibliography_treatment_ends_where_its_region_does():
    # As a mode trigger, "6. Literatur" fired once and persisted to the end of
    # the volume, so everything behind the bibliography was set as list
    # entries and its footnotes were never emitted. Behind the regions the
    # treatment is the region's.
    from scriptor.reflow.core import assign_treatment
    from scriptor.reflow.regions import assign_regions

    literatur = _list_page()
    literatur.body_lines.insert(0, "6. Literatur")
    pages = ([_prose_page(70, 15) for _ in range(4)] + [literatur, _list_page()]
             + [_prose_page(70, 15) for _ in range(8)])
    for k, p in enumerate(pages):
        p.label, p.label_source = str(k + 1), "printed"
    assign_modes(pages)
    assert all(p.mode == "main" for p in pages)
    assign_regions(pages)
    assert [p.region for p in pages[4:6]] == ["bibliography"] * 2

    assert assign_treatment(pages) == {"entries-versal": 2}
    assert [p.mode for p in pages[4:6]] == ["entries-versal"] * 2
    assert all(p.mode == "main" for p in pages[6:])


def _run(region: str, heading: str | None = None, n: int = 2) -> list[Page]:
    pages = [_list_page() for _ in range(n)]
    if heading:
        pages[0].body_lines.insert(0, heading)
    for p in pages:
        p.mode, p.region = "main", region
    return pages


def test_each_list_region_is_set_by_its_own_heading():
    # An index behind the bibliography is not set as entries because the
    # bibliography was: its own heading decides, and without the form it keeps
    # the running-text treatment like any other region.
    from scriptor.reflow.core import assign_treatment

    pages = (_run("bibliography", "6. Literatur") + _run("index")
             + _run("abbreviations", "7. Abkürzungsverzeichnis")
             + _run("index", "8. Personenregister"))
    assert assign_treatment(pages) == {"entries-versal": 2, "raw": 4}
    assert [p.mode for p in pages] == (["entries-versal"] * 2 + ["main"] * 2
                                       + ["raw"] * 4)


def test_the_form_on_a_later_page_of_the_run_sets_nothing():
    from scriptor.reflow.core import assign_treatment

    pages = _run("bibliography", n=3)
    pages[1].body_lines.insert(0, "6. Literatur")
    assert assign_treatment(pages) == {}
    assert all(p.mode == "main" for p in pages)


def test_a_list_treatment_leaves_measured_front_matter_alone():
    from scriptor.reflow.core import assign_treatment

    pages = _run("abbreviations", "1. Abkürzungsverzeichnis", n=3)
    pages[0].mode, pages[1].mode = "frontmatter", "toc"
    assert assign_treatment(pages) == {"raw": 1}
    assert [p.mode for p in pages] == ["frontmatter", "toc", "raw"]


def test_a_literature_section_in_running_text_takes_no_treatment():
    # Klinghardt: two parts in one PDF, and the introduction to part II has a
    # numbered section "3. Literatur" on the works it draws on. As a mode
    # trigger it set all 831 pages behind it as list entries; the regions read
    # it as running text, and so does the treatment now.
    from scriptor.reflow.core import assign_treatment

    pages = _run("main", "3. Literatur", n=4)
    assert assign_treatment(pages) == {}
    assert all(p.mode == "main" for p in pages)


def test_a_bare_sources_heading_takes_no_treatment():
    # "N. Quellen" was a raw trigger; the region vocabulary names no bare
    # "Quellen", so such a page has no region and no treatment.
    from scriptor.reflow.core import assign_treatment

    pages = _run("main", "5. Quellen")
    assert assign_treatment(pages) == {}
    assert all(p.mode == "main" for p in pages)


def test_calibrate_fallback_on_empty_histogram():
    # No main pages at all -> must not return 0 (which would suppress all
    # paragraph breaks); a sane positive fallback is required.
    pages = [Page(-1, ["kurz"], {}, mode="frontmatter")]
    threshold, hist = calibrate_threshold(pages)
    assert threshold >= CALIB_FALLBACK_MIN


def test_calibrate_normal_still_works():
    pages = [Page(-1, ["x" * 70 for _ in range(20)], {}, mode="main")]
    threshold, hist = calibrate_threshold(pages)
    assert threshold > 0 and hist
