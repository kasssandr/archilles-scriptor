"""Band metadata: source.json and selection.json.

A band's licence class decides where everything about it may live, so a
malformed or missing licence must fail loudly at load time rather than let
protected text drift into a committed directory.

Selections address pages *physically*. The printed label is what the metrics
measure, but it is a reading of the page, not a property the file can be
asked for -- the catalogue may be absent, partial, or plainly disagree with
what is printed. So the selection names PDF pages and the operator supplies
the labels while looking at them.
"""
from pathlib import Path

import pytest

from scriptor.eval.corpus import (
    CorpusError,
    band_root,
    loads_selection,
    loads_source,
)

SOURCE = """
{
  "band_id": "mueller2019",
  "url": "https://library.oapen.org/bitstream/handle/x/mueller.pdf",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "license": "CC-BY-4.0",
  "license_class": "free",
  "bibliography": "Mueller, Anna. 2019. A Title. A Press.",
  "matrix_rows": [1, 3]
}
"""

SELECTION = """
{
  "band_id": "mueller2019",
  "seed": 42,
  "body_range": [15, 340],
  "sampled": [21, 88, 134],
  "targeted": [
    {"page": 203, "reason": "note runs over onto the next page"}
  ]
}
"""


def test_source_parses():
    m = loads_source(SOURCE)
    assert m.band_id == "mueller2019"
    assert m.license_class == "free"
    assert m.matrix_rows == [1, 3]


def test_selection_parses_and_orders_pages():
    s = loads_selection(SELECTION)
    assert s.seed == 42
    assert s.body_range == (15, 340)
    assert s.sampled == [21, 88, 134]
    assert s.targeted[0].page == 203
    # every page the operator has to author, sampled before targeted
    assert s.all_pages == [21, 88, 134, 203]


def test_selected_pages_are_physical_numbers():
    s = loads_selection(SELECTION)
    assert all(isinstance(p, int) for p in s.all_pages)


def test_targeted_page_needs_a_reason():
    bad = SELECTION.replace('"reason": "note runs over onto the next page"',
                            '"reason": ""')
    with pytest.raises(CorpusError):
        loads_selection(bad)


def test_selected_page_outside_the_body_range_is_refused():
    bad = SELECTION.replace("[21, 88, 134]", "[21, 88, 999]")
    with pytest.raises(CorpusError):
        loads_selection(bad)


def test_a_page_must_not_be_selected_twice():
    bad = SELECTION.replace('{"page": 203,', '{"page": 88,')
    with pytest.raises(CorpusError):
        loads_selection(bad)


@pytest.mark.parametrize("mutation", [
    ('"license_class": "free"', '"license_class": "whatever"'),
    ('"license": "CC-BY-4.0"', '"license": ""'),
    ('"sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"',
     '"sha256": "tooshort"'),
])
def test_invalid_source_is_refused(mutation):
    old, new = mutation
    with pytest.raises(CorpusError):
        loads_source(SOURCE.replace(old, new))


def test_band_root_follows_licence_class():
    free = loads_source(SOURCE)
    protected = loads_source(SOURCE.replace('"free"', '"protected"'))
    corpus, local = Path("eval/corpus"), Path("eval/golden-local")
    assert band_root(free, corpus, local) == corpus / "mueller2019"
    assert band_root(protected, corpus, local) == local / "mueller2019"
