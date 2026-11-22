"""Added notes, "12a)": a note a volume set in after note 12 without
renumbering the ones behind it. Invented lines throughout."""
from scriptor.reflow.core import Page, notes_sidecar, parse_page
from scriptor.reflow.footnotes import NoteNo, follows, note_no


def test_an_added_note_counts_as_its_number_and_is_a_note_of_its_own():
    n = NoteNo(12, "f")
    assert int(n) == 12
    assert n != 12 and n == NoteNo(12, "f")
    assert hash(n) != hash(12) and hash(n) == hash(NoteNo(12, "f"))
    assert 12 < n < NoteNo(12, "g") < 13
    assert max([11, n, 12]) is n
    assert str(n) == "12f" and f"[{n}]" == "[12f]"
    assert n + 1 == 13 and type(n + 1) is int


def test_the_printed_form_reads_with_or_without_a_space():
    assert note_no("12") == 12 and type(note_no("12")) is int
    assert note_no("12f") == NoteNo(12, "f")
    assert note_no("36 a") == NoteNo(36, "a")


def test_an_added_note_follows_only_its_own_note():
    assert follows(NoteNo(12, "a"), 12)
    assert follows(NoteNo(12, "c"), NoteNo(12, "b"))
    assert follows(13, NoteNo(12, "c"))
    assert not follows(NoteNo(12, "a"), 11)
    assert not follows(NoteNo(12, "a"), NoteNo(12, "b"))
    assert not follows(NoteNo(197, "a"), 14)


def test_an_added_note_opens_in_a_block_on_bare_text():
    pg = parse_page(
        "Der Satz endet hier.\nEin zweiter Satz.\n"
        "12) Erste Note zum Satz.\n"
        "12a) Nachgetragene Note mit eigener Aussage.\n"
        "13) Die naechste Note.",
        last_note=11)
    assert set(pg.footnotes) == {12, NoteNo(12, "a"), 13}
    assert pg.footnotes[12] == "Erste Note zum Satz."
    assert pg.footnotes[NoteNo(12, "a")] == "Nachgetragene Note mit eigener Aussage."


def test_a_page_may_open_with_an_added_note_behind_the_note_read_last():
    pg = parse_page(
        "Der Satz endet hier.\nEin zweiter Satz.\n"
        "12b) Die zweite Nachtragsnote.\n"
        "12c) Die dritte Nachtragsnote.",
        last_note=40, last_read=NoteNo(12, "a"))
    assert set(pg.footnotes) == {NoteNo(12, "b"), NoteNo(12, "c")}


def test_a_page_does_not_open_with_an_added_note_behind_another_number():
    pg = parse_page(
        "Der Satz endet hier.\nEin zweiter Satz.\n"
        "12b) Die zweite Nachtragsnote.",
        last_note=40, last_read=40)
    assert pg.footnotes == {}


def test_a_reference_broken_over_the_line_stays_in_its_note():
    # "(Bl." / "197a)" is a folio broken off its abbreviation, behind note 14.
    pg = parse_page("Der Satz.\nNoch einer.", last_note=13, fn_block=[
        "14 Die Handschrift (Bl.",
        "197a) zeigt den Text.",
        "15 Die naechste Note.",
    ])
    assert set(pg.footnotes) == {14, 15}
    assert pg.footnotes[14] == "Die Handschrift (Bl. 197a) zeigt den Text."


def test_an_added_notes_marker_stays_text():
    pg = parse_page(
        "Der Satz Wort12a endet hier.\nEin zweiter Satz.\n"
        "12) Erste Note.\n"
        "12a) Nachgetragene Note.",
        last_note=11)
    assert "Wort12a" in " ".join(pg.body_lines)


def test_the_notes_sidecar_keeps_the_printed_number():
    page = Page(num=-1, body_lines=[], index=3)
    page.label = "7"
    out = notes_sidecar([(1, page, 12, False), (2, page, NoteNo(12, "f"), True)], [page])
    plain, added = out["notes"]
    assert plain["number"] == 12 and "printed" not in plain
    assert added["number"] == 12 and added["printed"] == "12f"
