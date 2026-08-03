"""Page selection must be reproducible and must stay inside the body range."""
import pytest

from scriptor.eval.authoring import PageRef, choose_pages


def _refs(n: int) -> list[PageRef]:
    """n physical pages; the first four carry roman labels like real frontmatter."""
    roman = ["i", "ii", "iii", "iv"]
    return [PageRef(index=i + 1, label=roman[i] if i < 4 else str(i - 3))
            for i in range(n)]


def test_same_seed_gives_same_pages():
    refs = _refs(60)
    a = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    b = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    assert a == b
    assert len(a) == 10


def test_different_seed_gives_different_pages():
    refs = _refs(60)
    a = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    b = choose_pages(refs, body_range=(5, 60), count=10, seed=7)
    assert a != b


def test_selection_stays_inside_body_range():
    refs = _refs(60)
    chosen = choose_pages(refs, body_range=(5, 20), count=8, seed=42)
    labels_in_range = {r.label for r in refs if 5 <= r.index <= 20}
    assert set(chosen) <= labels_in_range
    assert "i" not in chosen and "iv" not in chosen   # frontmatter excluded


def test_result_is_sorted_by_physical_order():
    refs = _refs(60)
    chosen = choose_pages(refs, body_range=(5, 60), count=10, seed=42)
    order = {r.label: r.index for r in refs}
    assert [order[c] for c in chosen] == sorted(order[c] for c in chosen)


def test_asking_for_more_than_available_is_refused():
    with pytest.raises(ValueError):
        choose_pages(_refs(60), body_range=(5, 10), count=20, seed=42)


def test_labels_are_returned_not_indices():
    chosen = choose_pages(_refs(60), body_range=(5, 60), count=3, seed=1)
    assert all(isinstance(c, str) for c in chosen)


# fetching -----------------------------------------------------------------

import hashlib

from scriptor.eval.authoring import ChecksumError, verify_checksum


def test_verify_checksum_accepts_matching_file(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.7 fake")
    digest = hashlib.sha256(b"%PDF-1.7 fake").hexdigest()
    verify_checksum(f, digest)          # must not raise


def test_verify_checksum_refuses_wrong_file(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.7 fake")
    with pytest.raises(ChecksumError):
        verify_checksum(f, "0" * 64)


def test_fetch_is_idempotent_when_file_already_matches(tmp_path, monkeypatch):
    from scriptor.eval import authoring
    from scriptor.eval.corpus import SourceMeta

    payload = b"%PDF-1.7 already here"
    dest = tmp_path / "source.pdf"
    dest.write_bytes(payload)
    meta = SourceMeta(
        band_id="b", url="https://example.invalid/x.pdf",
        sha256=hashlib.sha256(payload).hexdigest(),
        license="CC-BY-4.0", license_class="free", bibliography="B.",
    )

    def _explode(*a, **k):                     # downloading would be a bug here
        raise AssertionError("must not download when the file already matches")

    monkeypatch.setattr(authoring, "_download", _explode)
    assert authoring.fetch_pdf(meta, dest) == dest


# page material and skeleton ----------------------------------------------

import tomllib

from scriptor.eval.authoring import (
    read_page_refs,
    render_skeleton,
    write_page_material,
)
from scriptor.eval.corpus import loads_selection, loads_source

_SRC = """
{"band_id": "demo", "url": "https://example.invalid/d.pdf",
 "sha256": "%s", "license": "CC-BY-4.0", "license_class": "free",
 "bibliography": "Demo, D. 2020. Demo."}
""" % ("a" * 64)

_SEL = """
{"band_id": "demo", "seed": 42, "body_range": [1, 3],
 "label_source": "physical", "sampled": ["1", "3"],
 "targeted": [{"page": "2", "reason": "note runs over"}]}
"""


def _tiny_pdf(path):
    """Three pages of real text, so the textlayer has something to give."""
    import pymupdf
    doc = pymupdf.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {n + 1} body text for the corpus.")
    doc.save(path)
    doc.close()
    return path


def test_read_page_refs_falls_back_to_physical_numbers(tmp_path):
    pdf = _tiny_pdf(tmp_path / "d.pdf")
    refs, label_source = read_page_refs(pdf)
    assert [r.index for r in refs] == [1, 2, 3]
    assert [r.label for r in refs] == ["1", "2", "3"]
    assert label_source == "physical"


def test_write_page_material_emits_png_and_text(tmp_path):
    pdf = _tiny_pdf(tmp_path / "d.pdf")
    out = tmp_path / "pages"
    written = write_page_material(pdf, ["1", "3"], out, dpi=72)
    assert (out / "1.png").exists() and (out / "1.txt").exists()
    assert (out / "3.png").exists() and (out / "3.txt").exists()
    assert not (out / "2.png").exists()
    assert "body text" in (out / "1.txt").read_text(encoding="utf-8")
    assert len(written) == 4


def test_skeleton_is_valid_toml_listing_exactly_the_selected_pages():
    skel = render_skeleton(loads_source(_SRC), loads_selection(_SEL))
    parsed = tomllib.loads(skel)
    assert parsed["volume"] == "demo"
    assert parsed["pages"] == ["1", "3", "2"]
    assert "footnotes" not in parsed        # the sample block is commented out


def test_skeleton_carries_the_targeted_reason_as_a_hint():
    skel = render_skeleton(loads_source(_SRC), loads_selection(_SEL))
    assert "note runs over" in skel


# acceptance ---------------------------------------------------------------

from scriptor.eval.authoring import check_truth
from scriptor.eval.ground_truth import loads_truth

_SEL_CHECK = """
{"band_id": "demo", "seed": 42, "body_range": [1, 3],
 "label_source": "physical", "sampled": ["1", "2"], "targeted": []}
"""

_GOOD = '''
volume = "demo"
pages = ["1", "2"]
empty_pages = ["2"]

[[footnotes]]
page = "1"
num = 1
definition_starts = "A note long enough to be found"
status = "intact"
'''


def test_complete_band_passes():
    res = check_truth(loads_truth(_GOOD), loads_selection(_SEL_CHECK), _GOOD)
    assert res.ok and res.problems == []


def test_missing_selected_page_is_reported():
    bad = _GOOD.replace('pages = ["1", "2"]', 'pages = ["1"]').replace(
        'empty_pages = ["2"]\n', "")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("2" in p for p in res.problems)


def test_page_without_notes_and_without_empty_marker_is_reported():
    bad = _GOOD.replace('empty_pages = ["2"]\n', "")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("empty_pages" in p for p in res.problems)


def test_short_definition_is_reported():
    bad = _GOOD.replace("A note long enough to be found", "too short")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("definition_starts" in p for p in res.problems)


def test_duplicate_page_and_number_is_reported():
    bad = _GOOD + '''
[[footnotes]]
page = "1"
num = 1
definition_starts = "Another note, same printed number"
status = "intact"
'''
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("twice" in p or "duplicate" in p for p in res.problems)
