"""Region recall: how much of the apparatus a volume declares was named.

Until now the region work could only report how many pages *were* named. That
number cannot answer "is it enough?", because it has no denominator. These
metrics supply one, and they keep the two failure directions apart, because
they do not cost the same (spec §4.4): a region that stops early hides
nothing, a region that swallows body text hides a chapter.
"""
from scriptor.eval.adapters import parse_prepared
from scriptor.eval.ground_truth import loads_truth
from scriptor.eval.regions import evaluate_regions

# A volume of six pages: body to p. 3, then four pages of bibliography.
TRUTH = """
volume = "d"
pages = ["1"]

[[regions]]
from_page = "1"
name = "main"

[[regions]]
from_page = "4"
name = "bibliography"
"""


def _doc(*pages: tuple[str, str]) -> object:
    """Build prepared text from (region-marker-or-empty, page label) pairs."""
    parts = []
    for region, label in pages:
        if region:
            parts.append(f"[region: {region}]\n")
        parts.append(f"[p. {label}] Text of page {label}.\n\n")
    return parse_prepared("".join(parts))


def test_a_region_that_closes_early_is_found_but_incomplete():
    """Pouderon's case: the bibliography is seen, then closes after one page
    of twelve. Block-level says found, page-level says how much was lost."""
    doc = _doc(("main", "1"), ("", "2"), ("", "3"),
               ("bibliography", "4"), ("main", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    bib = [b for b in r.blocks if b.name == "bibliography"][0]
    assert (bib.pages, bib.named) == (3, 1)
    assert r.blocks_found == 2 and r.blocks_total == 2


def test_a_region_never_opened_is_a_missed_block():
    doc = _doc(("main", "1"), ("", "2"), ("", "3"), ("", "4"), ("", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    assert r.blocks_found == 1 and r.blocks_total == 2
    assert [b.name for b in r.blocks if b.named == 0] == ["bibliography"]


def test_a_fully_named_region_reaches_recall_one():
    doc = _doc(("main", "1"), ("", "2"), ("", "3"),
               ("bibliography", "4"), ("", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    assert r.exact_recall == 1.0
    assert r.false_apparatus == []


def test_body_text_swallowed_by_an_apparatus_region_is_the_expensive_defect():
    """Braunfels' "Abkürzungen:" mid-essay -- the failure §4.4 calls costly."""
    doc = _doc(("main", "1"), ("bibliography", "2"), ("", "3"),
               ("", "4"), ("", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    assert r.false_apparatus == ["2", "3"]


def test_an_apparatus_named_as_the_wrong_apparatus_still_serves_the_consumer():
    """ru_martyrs prints `contents` behind its index. Exact recall drops, but
    a retrieval consumer excluding apparatus is unharmed -- so both are kept
    apart rather than averaged into one misleading number."""
    doc = _doc(("main", "1"), ("", "2"), ("", "3"),
               ("index", "4"), ("", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    assert r.exact_recall < 1.0
    assert r.apparatus_recall == 1.0


def test_pages_before_the_first_boundary_are_not_counted():
    """A truth that starts at p. 1 says nothing about front matter printed
    before it; counting those pages would invent a denominator."""
    truth = loads_truth(TRUTH.replace('from_page = "1"', 'from_page = "2"'))
    doc = _doc(("", "1"), ("main", "2"), ("", "3"),
               ("bibliography", "4"), ("", "5"), ("", "6"))
    r = evaluate_regions(truth, doc)

    assert r.unclassified == 1
    assert r.exact_recall == 1.0


def test_a_boundary_the_output_never_prints_is_reported_not_silently_dropped():
    """If the page marker is missing the truth cannot be applied there. That
    is an output defect and has to be visible, not absorbed into the rate."""
    doc = _doc(("main", "1"), ("", "2"), ("", "3"), ("", "5"), ("", "6"))
    r = evaluate_regions(loads_truth(TRUTH), doc)

    assert r.unmatched_boundaries == ["4"]
