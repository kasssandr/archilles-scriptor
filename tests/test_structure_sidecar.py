"""The structure sidecar: what the master's six hashes cannot say (B4).

A run writes ``book.md.structure.json`` and ``.txt`` beside the pagination
sidecars, and the metadata block declares in one line how deep the volume
divides. The sidecar lists the master's own ``#`` lines, in their order --
that is the join a consumer reads it by -- and gives each its true depth, the
page it stands on and the witness that placed it.
"""
import json

import pytest

from scriptor.document import load_bundle
from scriptor.page import Box, Line, Span, SourcePage, dumps
from scriptor.reflow.core import main


PROSE = [
    "Die Ausgabe von {n} bleibt fuer den Text massgeblich bis heute im Streit.",
    "Auch die Randnotizen der Codices sind {n} mal untersucht worden, hier.",
    "Der Band sammelt die Belege von {n} in einem eigenen Anhang erneut auf.",
    "Damit endet der Abschnitt {n} und der naechste beginnt gleich danach da.",
    "Die Kollation der Handschrift {n} bestaetigt die Lesart der Aldina auch.",
    "Ein Nachtrag zu {n} verzeichnet die Varianten der juengeren Zeugen ganz.",
    "Der Herausgeber hat {n} an dieser Stelle gegen die Ueberlieferung gesetzt.",
    "Die Parallele bei {n} spricht eher fuer die Fassung des Laurentianus.",
    "Wer {n} liest, wird die Entscheidung der Ausgabe kaum bestreiten wollen.",
    "Ueber {n} ist damit das Noetige gesagt, und der Abschnitt schliesst hier.",
]

# Which physical page opens with which heading line.
HEADINGS = {
    12: "1. Die Ueberlieferung",
    16: "1.1 Die Handschriften",
    22: "2. Der Text",
}


def _frag(text, baseline, x0=50.0, size=9.0):
    box = Box(x0, baseline - 7.0, x0 + 6 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def _volume(tmp_path, headings=HEADINGS, pages=30):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for i in range(1, pages + 1):
        lines = [_frag(f"{100 + i}  JOSEPHUS UND DIE ANTIKE HISTORIOGRAPHIE", 20.0, x0=20.0)]
        y = 50.0
        if i in headings:
            lines.append(_frag(headings[i], y))
            y += 12
        for k in range(len(PROSE)):
            # Rotated per page: a wording that stood first on every page would
            # be read as a running head, numbers folded away.
            text = PROSE[(i + k) % len(PROSE)].format(n=len(PROSE) * i + k)
            # A section ends short, as print does it; otherwise the paragraph
            # runs on over the page break and swallows the heading below.
            if k == len(PROSE) - 1 and i + 1 in headings:
                text = "Damit endet er."
            lines.append(_frag(text, y + k * 12))
        page = SourcePage(index=i, width=300.0, height=200.0 + 12 * len(PROSE), source="pymupdf", lines=lines)
        (pages_dir / f"{i:08d}.json").write_text(dumps(page), encoding="utf-8")
    out = tmp_path / "buch.md"
    main(str(pages_dir), str(out))
    return out


def _sidecar(out):
    return json.loads((out.parent / "buch.md.structure.json").read_text(encoding="utf-8"))


def test_a_run_writes_the_structure_beside_the_pagination(tmp_path):
    out = _volume(tmp_path)
    assert (tmp_path / "buch.md.structure.json").exists()
    assert (tmp_path / "buch.md.structure.txt").exists()
    assert _sidecar(out)["version"] == 1


def test_the_sidecar_lists_the_headings_of_the_master_in_order(tmp_path):
    out = _volume(tmp_path)
    master = out.read_text(encoding="utf-8")
    hashes = [ln for ln in master.splitlines() if ln.startswith("#")]
    assert len(hashes) == 3
    assert [h["title"] for h in _sidecar(out)["headings"]] == [
        "Die Ueberlieferung", "Die Handschriften", "Der Text"]
    assert [h["depth"] for h in _sidecar(out)["headings"]] == [1, 2, 1]


def test_a_heading_knows_the_page_it_stands_on(tmp_path):
    out = _volume(tmp_path)
    assert [h["page"] for h in _sidecar(out)["headings"]] == ["112", "116", "122"]


def test_the_block_declares_the_division_in_one_line(tmp_path):
    out = _volume(tmp_path)
    block = out.read_text(encoding="utf-8").split("---")[1]
    assert "structure: 2 levels, chapters on level 1, 3 headings" in block


def test_both_masters_declare_the_same_division(tmp_path):
    out = _volume(tmp_path)

    def line(path):
        return next(ln for ln in path.read_text(encoding="utf-8").splitlines()
                    if ln.startswith("structure:"))

    assert line(out) == line(tmp_path / "buch.review.md")


def test_a_volume_without_a_heading_declares_no_division(tmp_path):
    out = _volume(tmp_path, headings={})
    assert "structure:" not in out.read_text(encoding="utf-8")
    assert not (tmp_path / "buch.md.structure.json").exists()


def test_the_report_shows_the_tree_and_the_schemes(tmp_path):
    _volume(tmp_path)
    report = (tmp_path / "buch.md.structure.txt").read_text(encoding="utf-8")
    assert "1. Die Ueberlieferung" in report
    assert "  1.1 Die Handschriften" in report      # indented by its depth
    assert "## Schemes" in report


def test_the_run_says_what_it_found(tmp_path, capsys):
    _volume(tmp_path)
    assert "Structure: 2 levels, chapters on level 1, 3 headings" in capsys.readouterr().err


# what the bundle reader makes of it --------------------------------------

def test_a_bundle_carries_the_structure_and_its_chapter_level(tmp_path):
    out = _volume(tmp_path)
    bundle = load_bundle(out)
    assert bundle.chapter_level == 1
    assert [n.depth for n in bundle.structure.headings] == [1, 2, 1]


def test_a_bundle_without_a_structure_sidecar_still_reads(tmp_path):
    out = _volume(tmp_path)
    (tmp_path / "buch.md.structure.json").unlink()
    bundle = load_bundle(out)
    assert bundle.structure is None and bundle.chapter_level is None


def test_a_structure_sidecar_of_an_unknown_version_is_refused(tmp_path):
    out = _volume(tmp_path)
    (tmp_path / "buch.md.structure.json").write_text('{"version": 99}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_bundle(out)
