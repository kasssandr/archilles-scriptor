"""A volume that numbers its notes past 999.

Bauer [10593] numbers its notes through the volume and prints 1320 of them.
From note 1000 on, the definition patterns (three digits at most) saw no
definition in the small-type block, so the block was not cut and the whole
apparatus of pp. 250-315 stayed in the running text -- 219 notes, some glued
into a word ("vorwegge1132 BVerfG"). Where a continuation line opened with a
small number ("17. April 2019"), that line was taken for a definition instead
and several notes were read as one. No admission check saw it: the audit never
knew the notes, and the text was all there.
"""
from scriptor.page import Box, Line, SourcePage, Span, dumps
from scriptor.reflow.core import main, parse_page
from scriptor.reflow.footnotes import match_definition, split_small_type_block

BODY = [
    "che Person. Auch juristische Personen koennen Grundrechtstraeger sein, da",
    "die Meinungsfreiheit ihrem Wesen nach auf sie anwendbar ist gem.",
    "Art. 19 Abs. 3 GG.1112",
    "Der Begriff der Meinung ist in Art. 5 Abs. 1 S. 1 GG grundsaetzlich weit",
    "zu verstehen.1113 Eine Meinung ist durch das Element der Stellungnahme",
    "gepraegt.",
]
NOTES = [
    "1112 BVerfG NJW 1989, S. 2877, 2877 – staatliche Pressefoerderung; BeckOK GG/",
    "Schemmer, 41. Ed. 2019, Art. 5 GG Rn. 2.",
    "1113 BeckOK GG/Schemmer, 41. Ed. 2019, Art. 5 GG Rn. 5.",
]


def test_a_four_digit_number_opens_a_definition():
    assert match_definition("1112 BVerfG NJW 1989, S. 2877, 2877 – staatliche Pressefoerderung")
    assert match_definition("1112) BVerfG NJW 1989, S. 2877.")
    assert match_definition("1112. BVerfG NJW 1989, S. 2877.")


def test_a_year_with_a_comma_still_continues_a_note():
    assert not match_definition("2017, S. 41, 42.")
    assert not match_definition("1958, S. 257, 259 – Lueth; BVerfG NJW 1995, S. 3303")


def test_the_block_of_a_page_past_note_999_is_cut():
    lines = BODY + NOTES
    sizes = [10.0] * len(BODY) + [8.7] * len(NOTES)
    split = split_small_type_block(lines, sizes, body_size=10.0)
    assert split is not None
    assert split.body == BODY
    assert split.notes == NOTES


def test_four_digit_notes_are_read_and_their_markers_placed():
    pg = parse_page("\n".join(BODY), fn_block=NOTES)
    assert set(pg.footnotes) == {1112, 1113}
    assert pg.footnotes[1112].endswith("Art. 5 GG Rn. 2.")
    body = "\n".join(pg.body_lines)
    assert "[1112]" in body and "[1113]" in body


def _frag(text, x0, baseline, size=10.0):
    box = Box(x0, baseline - 7.0, x0 + 4.5 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def test_four_digit_notes_reach_the_master_as_notes(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    lines = [_frag("265", 30, 20.0)]
    lines += [_frag(t, 30, 50.0 + 12.0 * i) for i, t in enumerate(BODY)]
    lines += [_frag(t, 30, 300.0 + 10.0 * i, size=8.7) for i, t in enumerate(NOTES)]
    page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf", lines=lines)
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")
    second = SourcePage(index=2, width=300.0, height=400.0, source="pymupdf", lines=[
        _frag("266", 30, 20.0),
        _frag("Die zweite Seite fuehrt den Text ohne Anmerkung weiter.", 30, 50.0),
    ])
    (pages_dir / "00000002.json").write_text(dumps(second), encoding="utf-8")

    out = tmp_path / "book.md"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    assert "1112 BVerfG" not in text and "1113 BeckOK" not in text
    assert "]: BVerfG NJW 1989, S. 2877" in text
    assert "]: BeckOK GG/Schemmer, 41. Ed. 2019, Art. 5 GG Rn. 5." in text
    assert text.count("[^") >= 4          # two anchors, two definitions
