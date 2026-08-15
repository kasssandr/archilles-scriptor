"""A folio rescued from a running footer is a witness, not an appended line.

A running footer carrying the page number is stripped as a unit, so the number
has to survive the strip (reflow/running_elements). Where the geometry cut the
apparatus, the footer sits inside the footnote block and the rescue happens
there.

Until stage 5 the rescued number was appended to the page text, which made it
indistinguishable from a folio the page prints in its own right -- and forced a
guard (`8c3254a`): Carlomagno's notes read "N Obra citada. Página NN." page
after page, so the note text passes as a running footer and the number rescued
from it is the *footnote* number. Appended, it landed behind the real folio at
the very foot of the page, and parse_page reads the last line: physical page 39
prints "41" and came out labelled "17", fifteen pages of the volume with it.

The guard could only ever say "not if the body already ends in something that
looks like a label". Now the rescue states its case like every other witness and
the fit decides, which is where a conflict between two readings belongs.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.verdict import run_verdict
from scriptor.reflow.pagination.witnesses import rescued_observations


def _page(index, label=None):
    return Page(num=-1, body_lines=["Text der Seite."], index=index,
                label_bottom=label)


def test_the_rescue_states_its_reading():
    obs = rescued_observations({7: "146"})
    assert [(o.pos, o.label, o.source) for o in obs] == [
        (7, "146", "printed-footer")
    ]


def test_the_rescue_weighs_less_than_the_page_itself():
    # It has been through a similarity match that decided the line was furniture
    # -- one step more than a folio the detector reads off the page.
    (o,) = rescued_observations({7: "146"})
    assert o.weight == 0.5


def test_nothing_is_stated_without_a_rescue():
    assert rescued_observations({7: None}) == []
    assert rescued_observations({}) == []


def test_a_rescued_folio_labels_a_page_that_prints_nothing_else():
    pages = [_page(1, "144"), _page(2, "145"), _page(3), _page(4, "147")]
    run_verdict(pages, rescued={3: "146"})
    assert [p.label for p in pages] == ["144", "145", "146", "147"]
    assert pages[2].label_source == "printed"


def test_the_printed_folio_wins_against_a_rescued_footnote_number():
    # Carlomagno: the page prints "41" at its foot and the apparatus yields
    # "17". Both are stated; the sequence settles it, and no guard is needed.
    pages = [_page(1, "39"), _page(2, "40"), _page(3, "41"), _page(4, "42")]
    run_verdict(pages, rescued={3: "17"})
    assert [p.label for p in pages] == ["39", "40", "41", "42"]


def test_a_rescued_number_that_fits_nothing_labels_nothing():
    pages = [_page(1, "39"), _page(2, "40"), _page(3), _page(4, "42")]
    run_verdict(pages, rescued={3: "17"})
    assert pages[2].label == "41"      # the sequence, not the rescue


def test_without_a_rescue_the_verdict_is_unchanged():
    pages = [_page(1, "39"), _page(2, "40"), _page(3), _page(4, "42")]
    run_verdict(pages)
    assert [p.label for p in pages] == ["39", "40", "41", "42"]
