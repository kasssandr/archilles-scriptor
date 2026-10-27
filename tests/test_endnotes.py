"""Endnotes (reflow/endnotes.py): the notes part read by its count, each note
hung on the page its marker stands on.

The cases are Meisel, *Der Mythus der herrschenden Klasse* (1962: printed
"[N]", notes "N Text" under "Zum N. Kapitel") and Van der Toorn, *Scribal
Culture* (2007: superscripts extracted as digits glued to their word, notes
"N. Text" under "1. Books That Are Not Books").
"""

from scriptor.reflow.core import Page, notes_sidecar
from scriptor.reflow.endnotes import apply_skeleton, bind, read_notes
from scriptor.reflow.headings import read_mark


def _stream(page, *lines):
    return [(page, ln) for ln in lines]


def _shape(part):
    return [(c.title, [n.number for n in c.notes]) for c in part.collections]


# --- read_notes ---------------------------------------------------------------

def test_the_count_opens_the_notes_and_a_head_opens_a_collection():
    part = read_notes(_stream(
        5, "ANMERKUNGEN", "Abkürzungen: TE = Teorica dei governi.",
        "Zur Einführung", "1 James Burnham, The Machiavellians, New York 1943.",
        "2 Isaac Deutscher, Russia in Transition, in: Dissent, II, 1955,",
        "S. 32.", "Zum 1. Kapitel", "1 Außer TE und EL: Dei rapporti fra il",
        "Parlamento, Palermo 1885.", "2 Gaetano Mosca and the Political Lessons."))
    assert _shape(part) == [("Zur Einführung", [1, 2]), ("Zum 1. Kapitel", [1, 2])]
    assert part.collections[0].notes[1].text.endswith("1955, S. 32.")
    assert [read_mark(s)[0] for s in part.skeleton[5]] == [
        "ANMERKUNGEN", "Abkürzungen: TE = Teorica dei governi.",
        "Zur Einführung", "Zum 1. Kapitel"]


def test_a_line_of_a_note_that_begins_with_1_starts_nothing():
    # "1 (1925)" continues note 3; the count goes on with 4.
    part = read_notes(_stream(
        1, "Zum 3. Kapitel", "1 TE, S. 53.", "2 A. a. O., S. 54.",
        "3 Siehe die Auflage von", "1 (1925), S. 12 ff.", "4 HK, S. 88."))
    assert _shape(part) == [("Zum 3. Kapitel", [1, 2, 3, 4])]
    assert part.collections[0].notes[2].text == "Siehe die Auflage von 1 (1925), S. 12 ff."


def test_a_head_the_ocr_reads_after_the_first_notes_is_the_collections():
    # Meisel p. 401: "1 Il Principe, Kap. XIX." / "Zum 4. Kapitel" / "2 …".
    part = read_notes(_stream(
        1, "Zum 3. Kapitel", "1 TE, S. 53.", "2 Politik, V. 4.",
        "3 Im Jahr 275 n. Chr. fiel die Wahl.",
        "1 Il Principe, Kap. XIX.", "Zum 4. Kapitel", "2 Das ist eine Anspielung."))
    assert [c.title for c in part.collections] == ["Zum 3. Kapitel", "Zum 4. Kapitel"]
    assert [n.number for n in part.collections[1].notes] == [1, 2]


def test_a_head_set_like_a_note_stands_over_its_first_note():
    # Van der Toorn: "1. Books That Are Not Books" directly over "1. From …",
    # and "2. Authorship in Antiquity" after the previous chapter's note 3.
    part = read_notes(_stream(
        2, "Notes", "Introduction", "1. See, e.g., Richard Elliot Friedman, Who Wrote the",
        "Bible? 2nd ed. (San Francisco: Harper, 1997).",
        "1. Books That Are Not Books", "1. From biblion, derived from biblos.",
        "2. 1 Macc 12:9 uses the expression ta biblia ta hagia.",
        "3. For an introduction to the subject, see Susan Niditch.",
        "2. Authorship in Antiquity", "1. So far as I have been able to ascertain.",
        "2. Charles Taylor, Sources of the Self."))
    assert _shape(part) == [("Introduction", [1]),
                            ("1. Books That Are Not Books", [1, 2, 3]),
                            ("2. Authorship in Antiquity", [1, 2])]
    assert read_mark(part.skeleton[2][0])[0] == "Notes"


def test_a_list_inside_a_note_is_not_the_count():
    # Meisel F.1: notes are "N Text", the list in it "N. Text".
    part = read_notes(_stream(
        1, "Zu den Folgerungen", "1 Zu Moscas Befürchtungen vgl. HK, S. 340. Nach Mannheim:",
        "1. Die Zahl der Eliten steige an;", "2. Wenn es zu viele Eliten gebe;",
        "2 Lawrence Dennis, The Dynamics of War.", "3 HK, S. 12.",
        "4 A. a. O., S. 13.", "5. Dorso, op. cit., S. 175 f.", "6 A. a. O., S. 174 f."))
    assert _shape(part) == [("Zu den Folgerungen", [1, 2, 3, 4, 5, 6])]
    assert "2. Wenn es zu viele" in part.collections[0].notes[0].text


# --- bind -----------------------------------------------------------------------

def _pages(*bodies):
    pages = []
    for i, body in enumerate(bodies):
        p = Page(num=i + 1, body_lines=list(body))
        p.label, p.index = str(i + 1), i + 1
        pages.append(p)
    return pages


def test_printed_markers_hang_their_notes_on_their_pages():
    pages = _pages(["Der Elitismus herrscht [1]. Und weiter [2]."],
                   ["Im Grunde [3]. Die Formel [ 1]."],
                   ["notes"])
    part = read_notes(_stream(2, "Zur Einführung", "1 Burnham.", "2 Deutscher.",
                              "3 Michels.", "Zum 1. Kapitel", "1 TE, S. 21."))
    apply_skeleton(pages, [2], part)
    bound = bind(pages, part, [0, 1])
    assert (bound.form, bound.found, bound.hanging) == ("printed", 4, 0)
    assert pages[0].footnotes == {1: "Burnham.", 2: "Deutscher."}
    assert pages[1].footnotes == {3: "Michels.", 1: "TE, S. 21."}
    assert pages[1].body_lines == ["Im Grunde [3]. Die Formel [1]."]
    assert pages[1].endnotes[1] == ("Zum 1. Kapitel", "3", 3)
    assert pages[2].notes_part and [read_mark(s)[0] for s in pages[2].body_lines] == [
        "Zur Einführung", "Zum 1. Kapitel"]


def test_glued_markers_are_set_off_and_numbers_of_the_text_left_alone():
    # "12:9" is a verse and "1997" a year; the markers are glued to words.
    pages = _pages(["Who wrote the Bible?1 See 1 Macc 12:9 in 1997.",
                    "a question of books.2 And of scribes,3 too."],
                   ["notes"])
    part = read_notes(_stream(1, "Introduction", "1. Friedman.", "2. Niditch.",
                              "3. Harris."))
    apply_skeleton(pages, [1], part)
    bound = bind(pages, part, [0])
    assert (bound.form, bound.found) == ("glued", 3)
    assert pages[0].body_lines == ["Who wrote the Bible? [1] See 1 Macc 12:9 in 1997.",
                                   "a question of books. [2] And of scribes, [3] too."]


def test_a_lost_marker_hangs_on_the_page_of_the_next_found_one():
    pages = _pages(["Erstens [1]."], ["Zweitens ohne Marker."], ["Drittens [3]."],
                   ["notes"])
    part = read_notes(_stream(3, "Zum 1. Kapitel", "1 Eins.", "2 Zwei.", "3 Drei."))
    apply_skeleton(pages, [3], part)
    bound = bind(pages, part, [0, 1, 2])
    assert (bound.found, bound.hanging) == (2, 1)
    assert pages[2].footnotes == {2: "Zwei.", 3: "Drei."}


def test_the_next_collection_begins_at_a_1_followed_by_its_2():
    # A stray "[1]" inside chapter one's run (a quoted "[1]") does not end it.
    pages = _pages(["a [1] b [2] c [1] d [3]"], ["e [1] f [2]"], ["notes"])
    part = read_notes(_stream(2, "Zum 1. Kapitel", "1 A.", "2 B.", "3 C.",
                              "Zum 2. Kapitel", "1 D.", "2 E."))
    apply_skeleton(pages, [2], part)
    bind(pages, part, [0, 1])
    assert pages[0].footnotes == {1: "A.", 2: "B.", 3: "C."}
    assert pages[1].footnotes == {1: "D.", 2: "E."}


def test_the_sidecar_names_the_collection_and_the_page_a_note_is_printed_on():
    pages = _pages(["Der Elitismus [1]."], ["notes"])
    part = read_notes(_stream(1, "Zur Einführung", "1 Burnham."))
    apply_skeleton(pages, [1], part)
    bind(pages, part, [0])
    side = notes_sidecar([(1, pages[0], 1, False)], pages)
    assert side["notes"][0] == {
        "id": 1, "number": 1, "synthetic": False,
        "anchor": {"label": "1", "occurrence": 1, "position": 1},
        "collection": "Zur Einführung",
        "printed_on": {"label": "2", "occurrence": 1, "position": 2},
    }
