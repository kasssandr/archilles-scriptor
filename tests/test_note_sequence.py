"""A note follows the note before it -- within its block.

The rule of the four-digit fix, carried down to every number (user, 19.9.:
"das sollte analog auch für kleinere Nummern gelten"). Inside a note, a line
can open with a small number that is no note: a page number the citation
broke before ("BGH GRUR 2017, S. 390," / "393 Rn. 10 ff."), a day before its
month ("... vom" / "17. April 2019"). Read as definitions they cut the note
they belong to and stood as notes of their own -- Bauer had 30 of them, 1350
definitions for 1320 printed notes.

The rule holds within a block: after note 530 the same page can go on with
531, or start the count again (a chapter that begins mid-page), and nothing
else. Carried from page to page it broke: one misread number set the course
for every page after it, and A comemoração kept 24 of its 117 note blocks
(A/B of 19.9.). A page's first note stays free below 1000 -- that is where a
count restarts -- and past 999 has to continue the volume's highest note.
"""
from scriptor.reflow.core import parse_page
from scriptor.reflow.footnotes import continues, follows


def test_a_note_follows_the_note_before_it():
    assert follows(531, 530)
    assert follows(1112, 1111)


def test_a_number_behind_the_note_before_is_no_note():
    assert not follows(393, 530)          # a page of a citation
    assert not follows(17, 1173)          # a day of a date
    assert not follows(530, 530)          # the same number again
    assert not follows(1958, 45)          # a year


def test_the_count_may_start_again_within_a_block():
    assert follows(1, 530)                # a chapter that begins mid-page
    assert follows(2, 45)                 # whose note 1 was unreadable
    assert not follows(4, 45)


def test_a_pages_first_note_is_free_below_1000():
    assert continues(12, None)
    assert continues(1, 530)              # a new chapter on a new page
    assert continues(17, 1173)            # and a slip there sets no course
    assert not continues(1958, 45)


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


def test_a_number_at_the_head_of_a_block_does_not_close_it():
    """Bauer: the block opened with the tail of the note before ("2. Aufl.
    ..."), that was taken for note 2, and 249, 250, 251 followed nothing. The
    block's notes are its longest run that follows through."""
    pg = parse_page("Text.249 Mehr.250 Ende.251", last_note=248, fn_block=[
        "2. Aufl. 2018, S. 12.",
        "249 Ein Flashmob ist ein Phaenomen, bei dem sich eine Gruppe trifft.",
        "250 Vgl. dazu S. 211 ff.",
        "251 BGH GRUR 2013, S. 618.",
    ])
    assert set(pg.footnotes) == {249, 250, 251}
    assert pg.fn_continuation == "2. Aufl. 2018, S. 12."


def test_a_note_whose_number_lost_a_digit_is_still_a_note():
    """Le trasformazioni p. 96: '151' read as "15 '". It is the next note in
    the block, not the next line of note 150."""
    pg = parse_page("Text.150 Mehr.151", last_note=149, fn_block=[
        "150 PLRE I, Fabiola 2, p. 323; PCBE It., Fabiola 1, p. 734 sg.",
        "15 '.Hier. Ep. 77, 2.",
    ])
    assert set(pg.footnotes) == {150, 15}
    assert pg.footnotes[150].endswith("p. 734 sg.")


def test_a_number_already_read_in_the_block_overwrites_nothing():
    pg = parse_page("Text.12 Mehr.13", last_note=11, fn_block=[
        "12 Erste Note, die weitergeht auf",
        "12 f. und endet dort.",
        "13 Zweite Note.",
    ])
    assert set(pg.footnotes) == {12, 13}
    assert pg.footnotes[12] == "Erste Note, die weitergeht auf 12 f. und endet dort."


def test_a_misreading_on_one_page_does_not_close_the_next():
    """The naive rule's failure: a caption read as note 3 set the count back,
    and the next page's 250 no longer continued anything."""
    caption = parse_page("Abbildung.3", last_note=249, fn_block=["3 Abbildung nach Warhol."])
    assert set(caption.footnotes) == {3}
    after = parse_page("Weiter im Text.250", last_note=max(249, *caption.footnotes),
                       fn_block=["250 BVerfG NJW 1989, S. 2877."])
    assert set(after.footnotes) == {250}
