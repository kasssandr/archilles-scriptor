"""Page selection must be reproducible and must stay inside the body range."""
import pytest

from scriptor.eval.authoring import PageRef, choose_pages


def _refs(n: int) -> list[PageRef]:
    """n physical pages; only some carry a catalogue label, as in real files."""
    return [PageRef(index=i + 1, catalogue_label=(str(i - 3) if i >= 4 else None))
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
    chosen = choose_pages(_refs(60), body_range=(5, 20), count=8, seed=42)
    assert all(5 <= p <= 20 for p in chosen)


def test_result_is_sorted_and_physical():
    chosen = choose_pages(_refs(60), body_range=(5, 60), count=10, seed=42)
    assert chosen == sorted(chosen)
    assert all(isinstance(p, int) for p in chosen)


def test_asking_for_more_than_available_is_refused():
    with pytest.raises(ValueError):
        choose_pages(_refs(60), body_range=(5, 10), count=20, seed=42)


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
 "sampled": [1, 3],
 "targeted": [{"page": 2, "reason": "note runs over"}]}
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


def test_read_page_refs_reports_missing_catalogue_labels_as_none(tmp_path):
    pdf = _tiny_pdf(tmp_path / "d.pdf")
    refs = read_page_refs(pdf)
    assert [r.index for r in refs] == [1, 2, 3]
    # a generated PDF has no PageLabels; that must not be papered over
    assert [r.catalogue_label for r in refs] == [None, None, None]


def test_page_material_is_named_by_physical_page(tmp_path):
    pdf = _tiny_pdf(tmp_path / "d.pdf")
    out = tmp_path / "pages"
    written = write_page_material(pdf, [1, 3], out, dpi=72)
    assert (out / "p001.png").exists() and (out / "p001.txt").exists()
    assert (out / "p003.png").exists() and (out / "p003.txt").exists()
    assert not (out / "p002.png").exists()
    assert "body text" in (out / "p001.txt").read_text(encoding="utf-8")
    assert len(written) == 4


def test_page_material_refuses_a_page_outside_the_document(tmp_path):
    pdf = _tiny_pdf(tmp_path / "d.pdf")
    with pytest.raises(ValueError):
        write_page_material(pdf, [99], tmp_path / "pages", dpi=72)


def test_skeleton_is_valid_toml_with_an_empty_page_list():
    skel = render_skeleton(loads_source(_SRC), loads_selection(_SEL),
                           {1: None, 2: "ii", 3: None})
    parsed = tomllib.loads(skel)
    assert parsed["volume"] == "demo"
    # the operator fills these in from the page images; nothing is guessed
    assert parsed["pages"] == []
    assert parsed["physical_pages"] == {}


def test_skeleton_lists_every_selected_physical_page():
    skel = render_skeleton(loads_source(_SRC), loads_selection(_SEL),
                           {1: None, 2: "ii", 3: None})
    for name in ("p001.png", "p002.png", "p003.png"):
        assert name in skel


def test_skeleton_offers_the_catalogue_label_only_as_a_hint():
    skel = render_skeleton(loads_source(_SRC), loads_selection(_SEL),
                           {1: None, 2: "ii", 3: None})
    assert "catalogue says" in skel and '"ii"' in skel
    assert "note runs over" in skel


# acceptance ---------------------------------------------------------------

from scriptor.eval.authoring import check_truth
from scriptor.eval.ground_truth import loads_truth

_SEL_CHECK = """
{"band_id": "demo", "seed": 42, "body_range": [1, 3],
 "sampled": [1, 2], "targeted": []}
"""

_GOOD = '''
volume = "demo"
pages = ["11", "12"]
empty_pages = ["12"]

[physical_pages]
"11" = 1
"12" = 2

[[footnotes]]
page = "11"
num = 1
definition_starts = "A note long enough to be found"
status = "intact"
'''


def test_complete_band_passes():
    res = check_truth(loads_truth(_GOOD), loads_selection(_SEL_CHECK), _GOOD)
    assert res.ok and res.problems == []


def test_selected_physical_page_without_a_label_is_reported():
    bad = _GOOD.replace('"12" = 2\n', "").replace(
        'pages = ["11", "12"]', 'pages = ["11"]').replace(
        'empty_pages = ["12"]\n', "")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("physical page 2" in p for p in res.problems)


def test_label_without_a_physical_page_is_reported():
    bad = _GOOD.replace('"12" = 2\n', "")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("physical_pages" in p for p in res.problems)


def test_physical_page_that_was_never_selected_is_reported():
    bad = _GOOD.replace('"12" = 2', '"12" = 3')
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("never selected" in p for p in res.problems)


def test_page_without_notes_and_without_empty_marker_is_reported():
    bad = _GOOD.replace('empty_pages = ["12"]\n', "")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("empty_pages" in p for p in res.problems)


def test_short_definition_is_reported():
    bad = _GOOD.replace("A note long enough to be found", "too short")
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("definition_starts" in p for p in res.problems)


def test_a_note_that_is_short_because_it_ends_there_is_accepted():
    # Bauer p. 63 prints "178 A.a.O., S. 21." and nothing more. Demanding more
    # characters than the page holds would make a correct truth unacceptable;
    # recording where the note ends is what says it was copied whole.
    short = _GOOD.replace(
        'definition_starts = "A note long enough to be found"',
        'definition_starts = "A.a.O., S. 21."\n'
        'definition_ends = "A.a.O., S. 21."',
    )
    res = check_truth(loads_truth(short), loads_selection(_SEL_CHECK), short)
    assert res.ok, res.problems


def test_duplicate_page_and_number_is_reported():
    bad = _GOOD + '''
[[footnotes]]
page = "11"
num = 1
definition_starts = "Another note, same printed number"
status = "intact"
'''
    res = check_truth(loads_truth(bad), loads_selection(_SEL_CHECK), bad)
    assert not res.ok
    assert any("twice" in p or "duplicate" in p for p in res.problems)


# cli ----------------------------------------------------------------------

from scriptor.cli import main


def test_cli_author_creates_selection_skeleton_and_material(tmp_path, capsys):
    band = tmp_path / "demo"
    band.mkdir()
    (band / "source.json").write_text(_SRC, encoding="utf-8")
    _tiny_pdf(band / "source.pdf")

    rc = main(["eval", "author", "--band", str(band), "--sample", "2",
               "--seed", "42", "--dpi", "72"])
    assert rc == 0
    assert (band / "selection.json").exists()
    assert (band / "truth.toml").exists()
    assert len(list((band / "pages").glob("p*.png"))) == 2


def test_cli_author_never_overwrites_existing_truth(tmp_path):
    band = tmp_path / "demo"
    band.mkdir()
    (band / "source.json").write_text(_SRC, encoding="utf-8")
    _tiny_pdf(band / "source.pdf")
    main(["eval", "author", "--band", str(band), "--sample", "2",
          "--seed", "42", "--dpi", "72"])
    (band / "truth.toml").write_text('volume="demo"\npages=[]\n', encoding="utf-8")

    main(["eval", "author", "--band", str(band), "--dpi", "72"])
    assert (band / "truth.toml").read_text(encoding="utf-8") == \
        'volume="demo"\npages=[]\n'


def test_cli_check_reports_problems_and_returns_nonzero(tmp_path, capsys):
    band = tmp_path / "demo"
    band.mkdir()
    (band / "source.json").write_text(_SRC, encoding="utf-8")
    (band / "selection.json").write_text(_SEL_CHECK, encoding="utf-8")
    (band / "truth.toml").write_text(
        _GOOD.replace('empty_pages = ["12"]\n', ""), encoding="utf-8")

    rc = main(["eval", "check", "--band", str(band)])
    assert rc == 1
    assert "empty_pages" in capsys.readouterr().err
