"""Where a volume's chapters begin, gathered from whoever knows.

Two customers, and they want different things from the same finding:

The *pagination plan* wants positions. A chapter opening is where a volume's
count may jump, so every confirmed start is a boundary candidate -- one more
costs nothing but arithmetic, and a subsection start is no worse a guess than
none.

The *recto witness* wants chapters, not subsections. "A chapter opens on an odd
page" is a claim about the top level of a book's structure; a subsection that
begins halfway down a page says nothing about it and would only dilute the
measurement. Hence the rank travels with the start, and the witness asks for
the level a volume actually opens its chapters on.

Measured over the eleven corpus volumes carrying an outline: asking only level 1
confirms 31 chapter starts, asking every level confirms 112. The publishers put
"Cover", "Inhoudsopgave" or the ISBN on level 1 and the chapters one level down.
"""

from scriptor.reflow.chapters import (
    ChapterStart,
    from_outline,
    principal_rank,
)
from scriptor.reflow.outline import OutlineEntry


def _pages(*page_texts):
    return [t.split("\n") for t in page_texts]


def test_a_start_is_taken_where_the_page_spells_out_the_title():
    entries = [OutlineEntry(1, "Die Uebergabe von Narbonne", 2)]
    pages = _pages("Vorspann", "Die Uebergabe von Narbonne\nDer Text beginnt.")
    assert from_outline(entries, pages) == [
        ChapterStart(pos=2, title="Die Uebergabe von Narbonne", rank=1,
                     source="outline")
    ]


def test_an_entry_the_page_does_not_confirm_is_dropped():
    # Same rule as the heading insertion: a catalogue that names a page is not
    # a page that shows the title.
    entries = [OutlineEntry(1, "Ein Kapitel", 2)]
    pages = _pages("Vorspann", "Etwas ganz anderes steht hier.")
    assert from_outline(entries, pages) == []


def test_every_level_is_asked_not_only_the_first():
    # Asclepios: level 1 holds "Cover" and "Inhoudsopgave", the chapters sit on
    # level 2. Asking level 1 alone found 2 starts in that volume; asking every
    # level finds 21.
    entries = [
        OutlineEntry(1, "Inhoudsopgave", 1),
        OutlineEntry(2, "Inleiding", 2),
        OutlineEntry(3, "Begindagen van de cultus", 3),
    ]
    pages = _pages("Inhoudsopgave", "Inleiding", "Begindagen van de cultus")
    assert [c.rank for c in from_outline(entries, pages)] == [1, 2, 3]


def test_a_page_named_twice_yields_one_start_at_the_highest_rank():
    # A chapter and its first subsection open on the same page. As a position
    # that is one place, and the coarser of the two ranks is the true one.
    entries = [
        OutlineEntry(1, "Kapitel", 1),
        OutlineEntry(2, "Erster Abschnitt", 1),
    ]
    pages = _pages("Kapitel\nErster Abschnitt\nText.")
    starts = from_outline(entries, pages)
    assert [(c.pos, c.rank) for c in starts] == [(1, 1)]


def test_starts_come_back_in_reading_order():
    entries = [
        OutlineEntry(2, "Zweites", 3),
        OutlineEntry(1, "Erstes", 2),
    ]
    pages = _pages("Vorspann", "Erstes", "Zweites")
    assert [c.pos for c in from_outline(entries, pages)] == [2, 3]


# --- which level a volume opens its chapters on -------------------------------

def test_the_principal_rank_is_the_level_carrying_the_most_starts():
    starts = [
        ChapterStart(2, "Inleiding", 2, "outline"),
        ChapterStart(9, "Context", 2, "outline"),
        ChapterStart(3, "Begindagen", 3, "outline"),
    ]
    assert principal_rank(starts) == 2


def test_a_lone_start_does_not_make_a_level_the_chapter_level():
    # eerste minister: one confirmed entry on level 1 against eleven on level 2.
    # The volume opens its chapters on level 2; the single level-1 entry is its
    # front matter, and letting it decide would leave the recto witness with one
    # observation.
    starts = ([ChapterStart(1, "Voorwerk", 1, "outline")]
              + [ChapterStart(p, f"Hoofdstuk {p}", 2, "outline")
                 for p in range(10, 21)])
    assert principal_rank(starts) == 2


def test_a_handful_on_a_coarser_level_does_not_outrank_a_full_set_below_it():
    # Asclepios: level 1 carries "Cover" and "Inhoudsopgave" -- two entries the
    # page happens to confirm -- while the nineteen chapters sit on level 2.
    # Taking the coarsest level with at least two starts would hand the recto
    # witness the front matter and none of the chapters.
    starts = ([ChapterStart(1, "Cover", 1, "outline"),
               ChapterStart(6, "Inhoudsopgave", 1, "outline")]
              + [ChapterStart(p, f"Hoofdstuk {p}", 2, "outline")
                 for p in range(10, 29)])
    assert principal_rank(starts) == 2


def test_a_tie_goes_to_the_coarser_level():
    # bauer-aneignung confirms seven on level 1 and seven on level 2. Where the
    # count cannot separate them, the coarser level is the one that means
    # "chapter".
    starts = ([ChapterStart(p, f"K{p}", 1, "outline") for p in range(1, 8)]
              + [ChapterStart(p, f"A{p}", 2, "outline") for p in range(20, 27)])
    assert principal_rank(starts) == 1


def test_without_starts_there_is_no_principal_rank():
    assert principal_rank([]) is None


# --- what the titles themselves say about their level -------------------------

def test_a_level_of_subsections_is_ruled_out_however_many_it_has():
    """The numbering in the title says what the entry is.

    "II.1" is a subsection of "II" and no count can make it a chapter. Asclepios
    numbers its subsections that way (10 on level 3, 3 more on level 4), Libros
    and A comemoração likewise -- and a volume can easily carry more subsections
    than chapters, which is exactly where counting alone would fail.
    """
    starts = ([ChapterStart(p, f"{p} Hoofdstuk", 2, "outline")
               for p in (10, 20, 30)]
              + [ChapterStart(p, f"{p//10}.{p%10} Onderdeel", 3, "outline")
                 for p in (11, 12, 13, 21, 22, 23, 31, 32)])
    assert principal_rank(starts) == 2


def test_a_level_that_is_only_packaging_is_ruled_out():
    # What the binder wrapped around the book, not how the book is divided.
    # Measured on level 1: "Cover" and "Half Title" (Oxford Handbook),
    # "Cubierta"/"Portada" (Libros), the bare ISBN twice (mehr-themistios).
    starts = ([ChapterStart(1, "Cover", 1, "outline"),
               ChapterStart(2, "Half Title", 1, "outline"),
               ChapterStart(3, "9783111013244", 1, "outline")]
              + [ChapterStart(p, f"{p} Chapter", 2, "outline")
                 for p in (10, 20)])
    assert principal_rank(starts) == 2


def test_where_the_titles_say_nothing_the_count_decides():
    """Asclepios is the case the titles cannot settle.

    Its level 1 holds "Inhoudsopgave" and "Verantwoording van de afbeeldingen" --
    parts of a book, not packaging, and not numbered either. What separates them
    from level 2 is that level 2 divides the whole volume and level 1 divides it
    into three parcels, which is a fact about counts, not about titles. So the
    count still decides here, and the comment says so rather than pretending the
    rule is stronger than it is.
    """
    starts = ([ChapterStart(1, "Inhoudsopgave", 1, "outline"),
               ChapterStart(2, "Verantwoording van de afbeeldingen", 1, "outline")]
              + [ChapterStart(p, f"Hoofdstuk {p}", 2, "outline")
                 for p in range(10, 29)])
    assert principal_rank(starts) == 2


def test_ruling_every_level_out_leaves_the_count_in_charge():
    # A volume of nothing but subsections still has to answer the question.
    starts = [ChapterStart(p, f"1.{p} Onderdeel", 3, "outline")
              for p in (10, 11, 12)]
    assert principal_rank(starts) == 3
