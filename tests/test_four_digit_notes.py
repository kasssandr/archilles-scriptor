"""A volume that numbers its notes past 999.

Bauer [10593] numbers its notes through the volume and prints 1320 of them.
From note 1000 on, the definition patterns (three digits at most) saw no
definition in the small-type block, so the block was not cut and the whole
apparatus of pp. 250-315 stayed in the running text -- 219 notes, some glued
into a word ("vorwegge1132 BVerfG"). Where a continuation line opened with a
small number ("17. April 2019"), that line was taken for a definition instead
and several notes were read as one. No admission check saw it: the audit never
knew the notes, and the text was all there.

Four digits alone are not the answer: a year breaks to the head of a line in
every bibliography ("(Paris," / "1958); J. H. W."), and the widened pattern
read 53 false notes out of L'Empire chrétien and 16 out of Militarizing Men
(A/B of 19.9.). A four-digit number opens a definition only where it
continues the volume's own numbering.
"""
from scriptor.page import Box, Line, SourcePage, Span, dumps
from scriptor.reflow.core import main, parse_page
from scriptor.reflow.footnotes import continues, match_definition, split_small_type_block

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


def test_a_four_digit_number_opens_a_definition_where_it_continues_the_numbering():
    assert match_definition("1112 BVerfG NJW 1989, S. 2877, 2877 – staatliche", 1111)
    assert match_definition("1112) BVerfG NJW 1989, S. 2877.", 1111)
    assert match_definition("1000. Siehe Lessig, Freie Kultur, 2006, S. 8, 19.", 999)


def test_a_year_at_the_head_of_a_line_opens_nothing():
    assert not match_definition("1958); J. H. W. G. Liebeschuetz, Antioch.", 45)
    assert not match_definition("1999 до 2002 г. было убито около 7 тыс. солдат", 120)
    assert not match_definition("1112 BVerfG NJW 1989, S. 2877.")   # nothing before it
    assert not continues(1958, 1112)                                  # too far ahead
    assert not continues(1100, 1112)                                  # behind


def test_a_small_number_is_read_as_before():
    assert match_definition("14.  Ut omnes homines eorum legis habeant")
    assert match_definition("275 So hat Raffael meist nur die Haende")
    assert not match_definition("2017, S. 41, 42.")
    assert not match_definition("1958, S. 257, 259 – Lueth; BVerfG NJW 1995, S. 3303")


def test_the_block_of_a_page_past_note_999_is_cut():
    lines = BODY + NOTES
    sizes = [10.0] * len(BODY) + [8.7] * len(NOTES)
    split = split_small_type_block(lines, sizes, body_size=10.0, last_note=1111)
    assert split is not None
    assert split.body == BODY
    assert split.notes == NOTES


def test_four_digit_notes_are_read_and_their_markers_placed():
    pg = parse_page("\n".join(BODY), fn_block=NOTES, last_note=1111)
    assert set(pg.footnotes) == {1112, 1113}
    assert pg.footnotes[1112].endswith("Art. 5 GG Rn. 2.")
    body = "\n".join(pg.body_lines)
    assert "[1112]" in body and "[1113]" in body


def test_a_year_that_broke_to_a_line_head_stays_in_its_note():
    pg = parse_page("Der Satz endet hier.45", last_note=44, fn_block=[
        "45. Festugiere, Antioche paienne et chretienne (Paris,",
        "1958); J. H. W. G. Liebeschuetz, Antioch.",
    ])
    assert set(pg.footnotes) == {45}
    assert pg.footnotes[45].endswith("(Paris, 1958); J. H. W. G. Liebeschuetz, Antioch.")


def _frag(text, x0, baseline, size=10.0):
    box = Box(x0, baseline - 7.0, x0 + 4.5 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def _page(index, label, body, notes):
    lines = [_frag(label, 30, 20.0)]
    lines += [_frag(t, 30, 50.0 + 12.0 * i) for i, t in enumerate(body)]
    lines += [_frag(t, 30, 300.0 + 10.0 * i, size=8.7) for i, t in enumerate(notes)]
    return SourcePage(index=index, width=300.0, height=400.0, source="pymupdf", lines=lines)


def test_four_digit_notes_reach_the_master_as_notes(tmp_path):
    """Across the page break where Bauer passes 999: the numbering the volume
    has reached is what lets 1000 and 1001 in."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    first = _page(1, "249", [
        "Die Kultur des Teilens wird von Fisher als Gegenmodell zu einer Ordnung",
        "beschrieben, in der jede Nutzung erst erlaubt werden muss, bevor sie",
        "stattfinden darf; er haelt beides fuer vereinbar.998 Die Vergütung soll",
        "dabei nicht an der einzelnen Kopie haengen, sondern an der Nutzung, die",
        "sich messen laesst, und das Werk selbst bliebe frei zugaenglich fuer",
        "alle, die es weiterverwenden wollen, ohne vorher zu fragen.999",
    ], ["998 Fisher, Property and Contract on the Internet, S. 1215.",
        "999 Ders., a.a.O., S. 1216."])
    second = _page(2, "250", [
        "Lessig nennt diese Ordnung eine freie Kultur und stellt ihr die Kultur",
        "der Erlaubnis gegenueber, in der das Recht den Zugang regelt.1000 Auch",
        "Senftleben sieht im Urheberrecht einen kulturellen Auftrag, der ueber",
        "den Schutz des einzelnen Werkes hinausgeht und die Bedingungen des",
        "Schaffens selbst betrifft, also auch die Moeglichkeit, auf Vorhandenes",
        "zurueckzugreifen, ohne jedes Mal um Erlaubnis bitten zu muessen.1001",
    ], ["1000 Siehe Lessig, Freie Kultur, 2006, S. 8, 19.",
        "1001 Senftleben, Der kulturelle Imperativ des Urheberrechts, in: Weller/",
        "Kemle/Dreier (Hrsg.), Kunst im Markt, 2014, S. 75."])
    for p in (first, second):
        (pages_dir / f"{p.index:08d}.json").write_text(dumps(p), encoding="utf-8")

    out = tmp_path / "book.md"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    assert "1000 Siehe" not in text and "1001 Senftleben" not in text
    assert "]: Siehe Lessig, Freie Kultur, 2006, S. 8, 19." in text
    assert "]: Senftleben, Der kulturelle Imperativ des Urheberrechts" in text
    assert text.count("]: ") == 4          # four definitions, none swallowed
