"""Margin notes as Disciplina sets them (Patzold, RU, 2026-11-15).

The folio "— 18 —", the run-over arrows "27, 28 >" / "< 27.", a list "1) … 13)"
inside a note, and the asterisk note on the title.
"""
import pytest

from scriptor.reflow.core import parse_page
from scriptor.reflow.footnotes import (
    drop_note_pointers,
    note_starts,
    pull_announced_notes,
)
from scriptor.reflow.pagelabel import detect_page_label
from scriptor.reflow.textlines import Reconstruction


# --- the dashed folio ---------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("— 18 —", "18"),
    ("– 249 –", "249"),
    ("- 7 -", "7"),
    ("— xiv —", "xiv"),
])
def test_dashed_folio(line, expected):
    assert detect_page_label(line) == expected


@pytest.mark.parametrize("line", [
    "— 18",              # one dash only: a dialogue line, an enumeration
    "18 —",
    "— 18 года —",       # words between the dashes
    "— v —",             # a lone roman character stays refused
])
def test_dashed_folio_stays_narrow(line):
    assert detect_page_label(line) is None


# --- a list inside a note -----------------------------------------------------

def test_list_in_another_convention_does_not_take_the_block():
    block = [
        "21. В их числе:",
        "1) Боэций Каорский;",
        "2) Леонтий из Оз;",
        "3) Секстилий Базаский;",
        "4) Адельфий Пиктавийский;",
        "22. Это: Авентин Шартрский.",
    ]
    assert [n for _i, n in note_starts(block, last=20)] == [21, 22]


def test_list_in_the_same_convention_is_still_a_restart():
    # A count that starts again in the volume's own convention is what a
    # chapter opening mid-page looks like; the new rule leaves it alone.
    block = ["21. Ende des Kapitels.", "1. Neue Zählung.", "2. Weiter."]
    assert [n for _i, n in note_starts(block, last=20)] == [21, 1, 2]


def test_first_count_wins_the_tie_before_any_note():
    block = ["Herrschaft um", "500 // Chlodwigs Welt.", "Прим. ред.", "1. Kreiner J."]
    assert [n for _i, n in note_starts(block, last=None)] == [1]


# --- run-over arrows ----------------------------------------------------------

def _rec(lines, size=8.0):
    return Reconstruction(lines=list(lines), measured=True, wide_gap_lines=0,
                          sizes=[size] * len(lines))


def test_arrows_are_taken_out_and_announcements_kept():
    recs = [
        _rec(["26. Боэций.", "27, 28 >"]),
        _rec(["< 27. Свидетельства о нем.", "< 28. A 506, P. 214.", "29. Avitus."]),
        _rec(["73. Начало ноты: >", "(73), 74 >"]),
        _rec(["< (73) «Beatissims igitur»", "<74. Martindale.", "< 57"]),
    ]
    touched, announced = drop_note_pointers(recs, body_size=12.0)
    assert announced == {0: {27, 28}, 2: {74}}
    assert recs[0].lines == ["26. Боэций."]
    assert recs[1].lines == ["27. Свидетельства о нем.", "28. A 506, P. 214.", "29. Avitus."]
    assert recs[2].lines == ["73. Начало ноты:"]
    assert recs[3].lines == ["«Beatissims igitur»", "74. Martindale."]
    assert all(len(r.lines) == len(r.sizes) == len(r.indents) == len(r.emphases)
               for r in recs)
    assert touched == 8


def test_arrows_need_the_habit():
    recs = [_rec(["12 >"]), _rec(["< 12. Note."])]
    assert drop_note_pointers(recs, body_size=12.0) == (0, {})
    assert recs[1].lines == ["< 12. Note."]


def test_arrows_in_body_type_are_the_authors():
    recs = [_rec(["1 >", "2 >"]), _rec(["< 3. Text"], size=12.0)]
    drop_note_pointers(recs, body_size=12.0)
    assert recs[1].lines == ["< 3. Text"]


def test_announced_notes_move_back_with_the_continuation():
    blocks = [
        ["72. Note.", "73. Begins here"],
        ["and goes on.", "74. Moved.", "75. Moved too.", "76. Stays."],
    ]
    assert pull_announced_notes(blocks, {0: {74, 75}}) == 2
    assert blocks[0] == ["72. Note.", "73. Begins here", "and goes on.",
                         "74. Moved.", "75. Moved too."]
    assert blocks[1] == ["76. Stays."]


def test_announcement_that_does_not_open_the_block_moves_nothing():
    blocks = [["26. Note."], ["40. Something else.", "41. Else."]]
    assert pull_announced_notes(blocks, {0: {27}}) == 0
    assert blocks[1] == ["40. Something else.", "41. Else."]


# --- the asterisk note --------------------------------------------------------

def test_asterisk_note_on_the_first_page_is_kept():
    page = parse_page(
        "около 500 года*\nСтатьи этого сборника civitas1 посвящены.",
        fn_block=["© Ш. Патцольд, 2017", "* Публикуется с разрешения автора.",
                  "1. Kreiner J. About the Bishop."],
        geometry_verified=True,
    )
    assert page.footnotes[0] == "Публикуется с разрешения автора."
    assert page.footnotes[1].startswith("Kreiner")
    assert page.fn_continuation is None
    assert any("©" in ln for ln in page.body_lines)


def test_leading_asterisk_without_marker_stays_a_continuation():
    page = parse_page(
        "Text ohne Sternchen.",
        fn_block=["* Fortsetzung einer Note.", "5. Neue Note."],
        geometry_verified=True, last_note=4,
    )
    assert 0 not in page.footnotes
    assert page.fn_continuation == "* Fortsetzung einer Note."
