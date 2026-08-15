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
    # imprint, Les apologistes 2005. Three volumes, the same trap -- and the
    # third of them sits on a page the mode assignment calls "main", which is
    # why the design's "before the main part" is not the test used here.
    got = _verdicts([_obs(1, "2020")], _pages(_page(1, mode="frontmatter")))
    assert got == ["year"]
    got = _verdicts([_obs(3, "2005")], _pages(_page(3, mode="main")))
    assert got == ["year"]


def test_a_number_a_volume_this_long_could_really_print_is_not_a_year():
    # The test is the volume's own extent: a book of 1300 pages has a page
    # 1200, so calling that a year would be an invention.
    pages = _pages(*(_page(i) for i in range(1, 1301)))
    assert _verdicts([_obs(1200, "1200")], pages) == ["unknown"]


def test_a_line_of_the_table_of_contents():
    # Carlomagno's contents page reads "V) EL SACRO IMPERIO ROMANO      169",
    # and 169 is a page of the book -- just not this one. La masonería's
    # contents does the same with 177.
    got = _verdicts([_obs(7, "169", source="printed-top")],
                    _pages(_page(7, mode="toc")))
    assert got == ["contents-page"]


def test_the_contents_and_the_plan_disagreeing_is_recorded_as_that():
    # Named for the disagreement and not for a culprit, because the contents is
    # often the one that is right. Gli Actus is the measured case: its contents
    # states INDICI on printed page 335, the plan states 336, and the volume
    # prints 335 there (hand analysis, 2026-08-15). The volume drops a blank
    # verso before that section, so the true stretch is one page long -- and a
    # one-page stretch cannot be attested twice, which is what min_attested
    # requires.
    got = _verdicts([_obs(352, "335", source="toc", weight=0.6)],
                    _pages(_page(352)))
    assert got == ["contents-disagrees"]


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
    # A chapter opening carries notes, and they start at 1 -- which is next door
    # to the chapter number. The apparatus must not claim a reading it never
    # produced: only a number rescued out of a running footer comes from there.
    pages = _pages(*(_page(p, footnotes={1: "Una nota.", 2: "Un'altra."})
                     for p in (67, 107, 155, 198)))
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
    got = _verdicts([_obs(39, "17", source="printed-footer", weight=0.5)],
                    _pages(_page(39, footnotes={17: "Obra citada."})))
    assert got == ["footnote-number"]


def test_a_number_from_the_edge_of_the_apparatus_counts_too():
    # The running footer sits below the apparatus, so the number taken out of it
    # is as often the note the page ends on as one it carries. Militarizing Men
    # rescues "17" from a page whose own notes begin at 18, and "41" from a page
    # carrying 43 and 44.
    got = _verdicts([_obs(110, "17", source="printed-footer", weight=0.5)],
                    _pages(_page(110, footnotes={18: "Ein Beleg."})))
    assert got == ["footnote-number"]
    got = _verdicts([_obs(120, "41", source="printed-footer", weight=0.5)],
                    _pages(_page(120, footnotes={43: "a", 44: "b"})))
    assert got == ["footnote-number"]


def test_a_note_further_away_does_not_claim_the_reading():
    got = _verdicts([_obs(120, "41", source="printed-footer", weight=0.5)],
                    _pages(_page(120, footnotes={60: "a"})))
    assert got == ["unknown"]


def test_the_neighbours_apparatus_counts_but_not_the_whole_volume():
    # A note that ran over the page break is defined on the next page.
    pages = _pages(_page(110), _page(111, footnotes={18: "Fortsetzung."}))
    got = _verdicts([_obs(110, "17", source="printed-footer", weight=0.5)], pages)
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
