"""A number opens a note only where it continues the numbering -- or starts it again.

The rule of the four-digit fix, carried down to every number (user, 19.9.:
"das sollte analog auch für kleinere Nummern gelten"). Inside a note, a line
can open with a small number that is no note: a page number the citation
broke before ("BGH GRUR 2017, S. 390," / "393 Rn. 10 ff."), a day before its
month ("... vom" / "17. April 2019"). Read as definitions they cut the note
they belong to and stood as notes of their own -- Bauer had 30 of them, 1350
definitions for 1320 printed notes.

Numbering restarts, though: per chapter, per part, per page. So a number
continues the note read last (at most MAX_NOTE_STEP past it) or starts the
count again (1, or 2 or 3 where the 1 was unreadable). Anything else is the
next line of the note before.
"""
from scriptor.reflow.core import parse_page
from scriptor.reflow.footnotes import continues


def test_a_number_continues_the_note_read_last():
    assert continues(531, 530)
    assert continues(12, None)            # the volume's first note
    assert not continues(1958, None)      # but not a year


def test_a_number_behind_the_note_read_last_is_no_note():
    assert not continues(393, 530)        # a page of a citation
    assert not continues(17, 1173)        # a day of a date
    assert not continues(530, 530)        # the same number again


def test_the_count_may_start_again():
    assert continues(1, 530)              # a new chapter
    assert continues(2, 45)               # whose note 1 was unreadable
    assert not continues(4, 45)


def test_a_page_number_at_the_head_of_a_note_line_stays_in_the_note():
    pg = parse_page("Der Satz traegt zwei Noten.530 Und noch eine.531", last_note=529,
                    fn_block=[
                        "530 BGH GRUR 2017, S. 390,",
                        "393 Rn. 10 ff. – Die Realitaet II.",
                        "531 Vgl. dazu S. 211 ff.",
                    ])
    assert set(pg.footnotes) == {530, 531}
    assert pg.footnotes[530] == "BGH GRUR 2017, S. 390, 393 Rn. 10 ff. – Die Realitaet II."


def test_a_date_that_broke_before_its_month_stays_in_the_note():
    pg = parse_page("Die Richtlinie.1173 Der EuGH.1174", last_note=1172, fn_block=[
        "1173 Richtlinie (EU) 2019/790 des Europaeischen Parlaments und des Rates vom",
        "17. April 2019 ueber das Urheberrecht und die verwandten Schutzrechte.",
        "1174 EuGH GRUR 2019, S. 929, 933 Rn. 72 – Pelham/Huetter.",
    ])
    assert set(pg.footnotes) == {1173, 1174}
    assert pg.footnotes[1173].endswith("vom 17. April 2019 ueber das Urheberrecht "
                                       "und die verwandten Schutzrechte.")


def test_a_volume_that_counts_per_page_starts_on_every_page():
    pg = parse_page("Erster Satz.1 Zweiter Satz.2", last_note=4,
                    fn_block=["1 Erste Note.", "2 Zweite Note."])
    assert set(pg.footnotes) == {1, 2}


def test_a_chapter_that_starts_mid_page_starts_the_count():
    pg = parse_page("Das Kapitel endet.45 Das naechste beginnt.1", last_note=44,
                    fn_block=["45. Letzte Note des Kapitels.", "1. Erste Note des neuen."])
    assert set(pg.footnotes) == {45, 1}
