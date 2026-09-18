"""``scriptor headings``: the second entrance (Gliederungsmodell §4.5, B4).

A master that is already edited must not be built again -- the edits would go
with it. This reads the volume's own contents list out of the finished master,
finds each entry where it stands in the text, and writes the ``#`` lines in,
and nothing else. It is the user's tool: ``scriptor_prepare.py`` never calls it.
"""
import json

import pytest

from scriptor.headings import mark_headings
from scriptor.pipeline import headings as run_headings

BLOCK = """---
format_version: 0.4.0
chunking_strategy: basic
pagination: bottom edge, 100% of pages attested
---
"""

CONTENTS = """[region: contents]

## Inhaltsverzeichnis

- [I. Die Ueberlieferung](#p-11) — p. 11
  - [A. Die Handschriften](#p-14) — p. 14
- [II. Der Text](#p-20) — p. 20

[region: main]
"""

BODY = """[p. 11] I. Die Ueberlieferung Ein erster Satz ueber die Codices und ihre Wege.

Ein zweiter Absatz, der nichts weiter mit der Gliederung zu schaffen hat hier.

[p. 14] A. Die Handschriften Der Laurentianus steht am Anfang der ganzen Reihe.

Noch ein Absatz, der die Lesarten der juengeren Zeugen ausfuehrlich bespricht.

[p. 20] II. Der Text Hier beginnt der zweite Teil der Untersuchung voellig neu.
"""

MASTER = BLOCK + "\n" + CONTENTS + "\n" + BODY


def _headings(text):
    return [ln for ln in text.splitlines() if ln.startswith("#")]


def test_every_entry_the_text_confirms_becomes_a_heading():
    out, structure, report = mark_headings(MASTER)
    assert _headings(out) == [
        "## Inhaltsverzeichnis",
        "# I. Die Ueberlieferung",
        "## A. Die Handschriften",
        "# II. Der Text",
    ]
    assert report.placed == 3


def test_a_heading_that_opens_a_page_stands_before_its_marker():
    out, _structure, _report = mark_headings(MASTER)
    assert "# I. Die Ueberlieferung\n\n[p. 11] Ein erster Satz" in out


def test_nothing_but_the_heading_lines_is_written():
    out, _structure, _report = mark_headings(MASTER)
    without = "".join(ln for ln in out.splitlines(keepends=True)
                      if not ln.startswith("# ") and not ln.startswith("## "))
    for sentence in ("Ein erster Satz ueber die Codices und ihre Wege.",
                     "Der Laurentianus steht am Anfang der ganzen Reihe.",
                     "Hier beginnt der zweite Teil der Untersuchung voellig neu.",
                     "Ein zweiter Absatz, der nichts weiter"):
        assert sentence in without


def test_a_second_run_changes_nothing():
    once, _s, _r = mark_headings(MASTER)
    twice, _s2, report = mark_headings(once)
    assert twice == once
    assert report.changed is False


def test_the_depth_is_the_one_the_list_indents_to():
    _out, structure, _report = mark_headings(MASTER)
    assert [(n.depth, n.title) for n in structure.headings] == [
        (2, "Inhaltsverzeichnis"),   # the list's own name, as render_toc sets it
        (1, "Die Ueberlieferung"),
        (2, "Die Handschriften"),
        (1, "Der Text"),
    ]


def test_an_entry_no_page_confirms_is_reported_and_not_written():
    master = MASTER.replace("- [II. Der Text](#p-20) — p. 20",
                            "- [II. Der Text](#p-20) — p. 20\n- [III. Der Anhang](#p-90) — p. 90")
    out, structure, report = mark_headings(master)
    assert "III. Der Anhang" not in "\n".join(_headings(out))
    assert report.unplaced == 1
    assert structure.unplaced[0]["text"] == "III. Der Anhang"


def test_a_heading_the_user_wrote_by_hand_stays_and_is_marked_stale():
    master = MASTER.replace("Ein zweiter Absatz, der nichts",
                            "### Eine eigene Zwischenzeile\n\nEin zweiter Absatz, der nichts")
    out, structure, _report = mark_headings(master)
    assert "### Eine eigene Zwischenzeile" in out
    stale = next(n for n in structure.headings if n.title == "Eine eigene Zwischenzeile")
    assert [w.source for w in stale.sources] == ["stale"]


def test_a_level_the_list_never_wrote_down_is_taken_as_the_one_below_it():
    master = MASTER.replace(
        "Noch ein Absatz, der die Lesarten der juengeren Zeugen ausfuehrlich bespricht.",
        "aa) Der Laurentianus\n\n"
        "Ein Absatz ueber diese Handschrift, der lang genug ist, um Prosa zu sein.\n\n"
        "bb) Der Marcianus\n\n"
        "Ein weiterer Absatz ueber die zweite Handschrift, ebenfalls lang genug.")
    out, structure, report = mark_headings(master)
    assert report.promoted == 2
    assert "### aa) Der Laurentianus" in out
    deep = next(n for n in structure.headings if n.title == "Der Laurentianus")
    assert deep.depth == 3 and [w.source for w in deep.sources] == ["numbering"]


def test_a_wording_inside_a_sentence_does_not_become_a_heading():
    """A volume whose chapters are called "Samuel", "Saul", "David" names them
    again in every other sentence; without the pages there is nothing but the
    line break to tell the heading from the prose (M1h 8081)."""
    master = MASTER.replace("- [II. Der Text](#p-20) — p. 20",
                            "- [Der Laurentianus](#p-20) — p. 20")
    master = master.replace(
        "[p. 20] II. Der Text Hier beginnt",
        "[p. 20] Zu nennen ist hier Der Laurentianus, und danach beginnt")
    out, _structure, report = mark_headings(master)
    assert "# Der Laurentianus" not in out
    assert report.placed == 2


def test_nothing_is_written_into_a_marker_or_a_note():
    """A volume whose contents names a chapter "Notes" had '# notes' written
    into '[region: notes]' (M1h 4631). Declaration is not text."""
    master = MASTER.replace("- [II. Der Text](#p-20) — p. 20",
                            "- [Der Laurentianus steht](#p-20) — p. 20")
    master = master.replace(
        "[p. 20] II. Der Text Hier beginnt der zweite Teil der Untersuchung voellig neu.",
        "[region: notes]\n\n[^1]: Der Laurentianus steht am Rand der Seite.")
    out, _structure, _report = mark_headings(master)
    assert "[region: notes]" in out and "# notes" not in out
    assert "[^1]: Der Laurentianus steht am Rand der Seite." in out


def test_a_heading_written_before_a_marker_is_found_on_its_page_again():
    """The heading moves in front of the marker, so the page it belongs to has
    to follow it there -- otherwise the second run looks for the entry on the
    next page and places it in the prose (spec §4.2)."""
    master = MASTER.replace(
        "Ein zweiter Absatz, der nichts weiter mit der Gliederung zu schaffen hat hier.",
        "Ein zweiter Absatz, der von I. Die Ueberlieferung noch einmal spricht hier.")
    once, _s, _r = mark_headings(master)
    twice, _s2, report = mark_headings(once)
    assert twice == once and report.changed is False


def test_the_block_declares_the_division_it_found():
    out, _structure, _report = mark_headings(MASTER)
    assert "structure: 2 levels, chapters on level 1, 4 headings" in out


def test_a_master_that_gains_a_structure_line_says_it_is_0_4_0():
    """The ``structure`` field is what 0.4.0 adds (spec §11); a block that
    carries it and still says 0.3.0 would declare a version that has no such
    field (decision of 18.9.)."""
    master = MASTER.replace("format_version: 0.4.0", "format_version: 0.3.0")
    out, _structure, report = mark_headings(master)
    assert "format_version: 0.4.0" in out and "0.3.0" not in out
    assert report.changed is True


def test_a_newer_format_version_is_not_lowered():
    master = MASTER.replace("format_version: 0.4.0", "format_version: 0.5.1")
    out, _structure, _report = mark_headings(master)
    assert "format_version: 0.5.1" in out


def test_a_master_left_alone_keeps_its_version():
    master = (BLOCK + "\n" + BODY).replace("format_version: 0.4.0", "format_version: 0.3.0")
    out, _structure, _report = mark_headings(master)
    assert out == master


def test_a_master_without_a_contents_list_is_left_alone():
    master = BLOCK + "\n" + BODY
    out, structure, report = mark_headings(master)
    assert out == master
    assert structure is None and report.placed == 0


# the command ------------------------------------------------------------

def test_the_command_writes_the_master_and_its_sidecar(tmp_path, capsys):
    master = tmp_path / "buch.md"
    master.write_text(MASTER, encoding="utf-8")
    run_headings(master)

    assert "# I. Die Ueberlieferung" in master.read_text(encoding="utf-8")
    sidecar = json.loads((tmp_path / "buch.md.structure.json").read_text(encoding="utf-8"))
    assert [h["title"] for h in sidecar["headings"]][1] == "Die Ueberlieferung"
    assert (tmp_path / "buch.md.structure.txt").exists()
    err = capsys.readouterr().err
    assert "3 of 3" in err


def test_the_command_writes_nothing_on_a_dry_run(tmp_path):
    master = tmp_path / "buch.md"
    master.write_text(MASTER, encoding="utf-8")
    run_headings(master, dry_run=True)
    assert master.read_text(encoding="utf-8") == MASTER
    assert not (tmp_path / "buch.md.structure.json").exists()


def test_the_command_refuses_a_file_that_is_not_a_bundle(tmp_path):
    master = tmp_path / "buch.md"
    master.write_text("Ein gewoehnliches Markdown ohne Block.\n", encoding="utf-8")
    with pytest.raises(ValueError):
        run_headings(master)
