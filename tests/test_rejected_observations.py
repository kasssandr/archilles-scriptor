"""What a rejected observation actually was.

An observation the winning plan contradicts is not noise: it is a line of the
book that looks like a page number and is not one. The classification exists for
the report -- nothing downstream acts on it -- so its job is to let a reader
check the verdict without opening the PDF.

Every case here is measured on the corpus. The categories were not chosen in
advance: they are what the eighteen volumes actually produced.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.observation import Observation
from scriptor.reflow.pagination.plan import PaginationPlan, Segment
from scriptor.reflow.pagination.rejected import classify


def _obs(pos, label, source="printed-bottom", weight=1.0):
    return Observation(pos=pos, label=label, source=source, weight=weight,
                       why="test")


def _page(index, mode="main", footnotes=None, lines=("Text.",)):
    p = Page(num=-1, body_lines=list(lines), index=index)
    p.mode = mode
    p.footnotes = dict(footnotes or {})
    return p


def _pages(*pages):
    return {p.index: p for p in pages}


def _verdicts(rejected, pages, plan=PaginationPlan()):
    return [r.verdict for r in classify(rejected, pages, plan)]


# ── the categories, one measured case each ───────────────────────────

def test_a_year_on_the_imprint_page():
    # A comemoração prints 2020 on its title page, L'Empire 1972 in its
    # imprint, Les apologistes 2005. Three volumes, the same trap.
    got = _verdicts([_obs(1, "2020")], _pages(_page(1, mode="frontmatter")))
    assert got == ["year"]


def test_a_number_that_is_a_page_of_the_book_is_not_a_year():
    got = _verdicts([_obs(1, "1200")], _pages(_page(1)))
    assert got == ["unknown"]


def test_a_line_of_the_table_of_contents():
    # Carlomagno's contents page reads "V) EL SACRO IMPERIO ROMANO      169",
    # and 169 is a page of the book -- just not this one. La masonería's
    # contents does the same with 177.
    got = _verdicts([_obs(7, "169", source="printed-top")],
                    _pages(_page(7, mode="toc")))
    assert got == ["contents-page"]


def test_a_cross_reference_the_contents_placed_wrongly():
    # The ToC witness says "this title is printed on page 335". Where the plan
    # disagrees, the title was found at the wrong position -- a failure of the
    # search, not of the volume.
    got = _verdicts([_obs(352, "335", source="toc", weight=0.6)],
                    _pages(_page(352)))
    assert got == ["contents-cross-reference"]


def test_a_numeral_the_scan_cut_short():
    # La masonería's roman front matter, seven times: the plan says XXII and the
    # page reads "XXI", XXVIII against "XXVII". The last I is missing from the
    # extraction, so the observation is a prefix of what the volume prints --
    # which is a misreading, not a different page.
    plan = PaginationPlan(segments=(
        Segment(start_pos=13, start_label="11", style="roman-upper"),
    ))
    got = _verdicts([_obs(24, "XXI", source="printed-geometric", weight=0.8)],
                    _pages(_page(24)), plan)
    assert got == ["truncated-numeral"]


def test_a_shorter_numeral_that_is_not_a_prefix_is_not_a_truncation():
    plan = PaginationPlan(segments=(
        Segment(start_pos=13, start_label="11", style="roman-upper"),
    ))
    got = _verdicts([_obs(24, "IX", source="printed-geometric", weight=0.8)],
                    _pages(_page(24)), plan)
    assert got == ["unknown"]


def test_a_chapter_number_standing_where_a_folio_would():
    # Gli Actus opens its chapters with a bare "2", "3", "4", "5" at the head of
    # the page -- the edge it paginates at. Singly each is unreadable; together
    # they are a numbering of their own, counting 1 while the pages count 40.
    #
    # The rule the design proposed (match against a ToC entry whose title is
    # confirmed on this page) does not fire here: none of the four positions is
    # a confirmed chapter opening. Measured, what identifies them is that they
    # form their own run.
    rejected = [_obs(67, "2", source="printed-top"),
                _obs(107, "3", source="printed-top"),
                _obs(155, "4", source="printed-top"),
                _obs(198, "5", source="printed-top")]
    pages = _pages(*(_page(p) for p in (67, 107, 155, 198)))
    assert _verdicts(rejected, pages) == ["chapter-number"] * 4


def test_two_are_enough_for_a_run():
    # Libros numbers its appendices "1" and "2" the same way.
    rejected = [_obs(295, "1", source="printed-top"),
                _obs(301, "2", source="printed-top")]
    pages = _pages(_page(295), _page(301))
    assert _verdicts(rejected, pages) == ["chapter-number"] * 2


def test_a_single_small_number_is_not_a_run():
    got = _verdicts([_obs(67, "2", source="printed-top")], _pages(_page(67)))
    assert got == ["unknown"]


def test_a_number_repeated_rather_than_counting_is_not_a_run():
    # Les apologistes reads "li" twice, ninety-six pages apart. Two of the same
    # value are not a numbering.
    rejected = [_obs(39, "li", source="printed-top"),
                _obs(135, "li", source="printed-bottom")]
    pages = _pages(_page(39), _page(135))
    assert _verdicts(rejected, pages) == ["unknown"] * 2


def test_a_footnote_number_at_the_foot_of_the_page():
    # Carlomagno's notes read "N Obra citada. Página NN." and the rescued folio
    # can be the note's own number. Once the rescue is a witness rather than an
    # appended line, this is what a rejected one looks like.
    got = _verdicts([_obs(39, "17", source="footer-rescue", weight=0.5)],
                    _pages(_page(39, footnotes={17: "Obra citada."})))
    assert got == ["footnote-number"]


def test_the_catalogue_disagreeing_is_named_as_such():
    # Artificial Humanities' catalogue counts its front matter one step out of
    # step with the printed pages. Worth naming: it is the one source whose
    # error is systematic rather than per-page.
    got = _verdicts([_obs(4, "iii", source="catalogue", weight=0.9)],
                    _pages(_page(4, mode="frontmatter")))
    assert got == ["catalogue"]


def test_what_nothing_explains_is_called_unknown():
    # Les apologistes prints genuine folios the plan cannot use, because the
    # volume is scanned two book pages to a sheet. Calling that anything but
    # unknown would be a guess dressed as a finding.
    got = _verdicts([_obs(29, "57", source="printed-top")], _pages(_page(29)))
    assert got == ["unknown"]


# ── what the classification carries ──────────────────────────────────

def test_a_rejection_says_what_the_plan_expected_instead():
    plan = PaginationPlan(segments=(
        Segment(start_pos=1, start_label="1", style="arabic"),
    ))
    (r,) = classify([_obs(67, "2", source="printed-top")], _pages(_page(67)),
                    plan)
    assert r.predicted == "67"
    assert r.observation.label == "2"


def test_a_position_the_plan_says_nothing_about_has_no_prediction():
    (r,) = classify([_obs(67, "2")], _pages(_page(67)), PaginationPlan())
    assert r.predicted is None


def test_the_order_is_the_reading_order_of_the_document():
    # The report is read next to the book, so it is sorted the way the book is
    # (memory: reports by position, with a searchable text sample).
    rejected = [_obs(198, "5"), _obs(67, "2"), _obs(107, "3")]
    pages = _pages(*(_page(p) for p in (67, 107, 198)))
    assert [r.observation.pos for r in classify(rejected, pages,
                                                PaginationPlan())] == [67, 107, 198]
