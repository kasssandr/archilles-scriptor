"""A note continued onto a line that opens with a number continues the note.

Fried, *Donation of Constantine and Constitutum Constantini* (De Gruyter 2007):
"10 (1889), pp. 302-25" under "… In: MIÖG". Read as a note, it took the
number, and six times the count could not tell -- 10 may follow 7 as well as 8
may. The notes hang their number 17pt left of the text, and a continuation
line starts where the text does.
"""

from scriptor.reflow.core import _assemble_footnotes
from scriptor.reflow.footnotes import (
    CONTINUES,
    definition_numbers,
    definition_start,
    hung_continuations,
    split_small_type_block,
)

# Fried p. 4, the foot of the page: number column at 79.4, text at 96.4.
NOTE_LINES = [
    "7   Paul Scheffer-Boichorst, Neuere Forschungen über die Konstantinische Schenkung. In: MIÖG",
    "10 (1889), pp. 302-25 and 11 (1890), pp. 128-46, reprinted in: idem, Gesammelte Schriften 1,",
    "Berlin 1903, pp. 1-63 (from which quotes are taken); the results were widely accepted.",
    "8   On discussions on authenticity and tradition, cf. Horst Fuhrmann, Konstantinische Schenkung",
    "und abendländisches Kaisertum. In: DA 22 (1966), pp. 63-178.",
]
HUNG = [79.44, 96.42, 96.42, 79.43, 96.41]
BODY = "The last line of the running text above the notes, set in the body's own type."


def test_a_line_on_the_continuation_edge_continues_its_note():
    assert hung_continuations(NOTE_LINES, HUNG, 8.52) == {1}


def test_a_block_set_flush_says_nothing():
    # Every start stands on the edge of the continuation lines: the count
    # decides, as it did before.
    flush = [79.4] * len(NOTE_LINES)
    assert hung_continuations(NOTE_LINES, flush, 8.52) == set()


def test_a_number_set_flush_with_its_text_is_no_hanging_number():
    # Right-aligned numbers: "9" stands half a digit in from "10" -- less
    # than an em off the continuation edge, so nothing is said.
    lines = ["9 Ibid., p. 12.", "10 Cf. the edition, as above,", "p. 44 and passim."]
    assert hung_continuations(lines, [83.6, 79.4, 79.4], 8.52) == set()


def test_a_quotation_above_the_first_note_does_not_set_the_edge():
    # Libros de no poco sobresalto p. 70: the small run took along a set-off
    # quotation at 73pt; note 22 opens there with a first-line indent and is
    # continued at 59pt, where "159) llama" -- a page of a citation -- stands.
    lines = ["Viendo los estragos y enormes daños que los civiles y bajos, groseros",
             "porquerizos con las crecidas manadas de sus colmilludos puercos en nues-",
             "tras dehesas y pastos cada día hacen, no solamente comiendo y devorando",
             "22 Nótese que estas coerciones aparecen ya en la obra inaugural. Refiere la",
             "voz poética de Sireno en el canto de la ninfa Dórida: «Mi amo, aquel gran pastor,",
             "/ es quien me hace partir» (II, p. 86, vv. 190-191). Torres Corominas (2021, p.",
             "159) llama la atención sobre este «gran pastor», trasunto del rey, en el mundo",
             "arcádico."]
    indents = [73.13, 73.13, 73.13, 73.13, 58.95, 58.95, 58.95, 58.95]
    assert hung_continuations(lines, indents, 9.5) == {6}


def test_the_next_number_opens_its_note_wherever_it_stands():
    # L'Empire chrétien p. 229: the scan set note 7 on the continuation edge;
    # it is the number after 6, and the count vouches for it.
    lines = ["5. Chron. Min. I, 243 et 297. — Selon un thème rhétorique. Théodose aurait",
             "à regret, Pacatus, i i ; Claudien, de IVcons. Honorii, 47. La date du",
             "6. Elu par le Sénat, dit Malalas, XIII, p. 344. Reconnu par le Sénat, dit Pacatus,",
             "7. Sur la reconnaissance par le Sénat de Constantinople, Thémist., Or. XIV."]
    assert hung_continuations(lines, [60.48, 44.64, 59.76, 44.64], 9.0, 4) == set()
    # The same line opening a number the count does not vouch for continues.
    lines[3] = "12. Sur la reconnaissance par le Sénat de Constantinople, Thémist., Or. XIV."
    assert hung_continuations(lines, [60.48, 44.64, 59.76, 44.64], 9.0, 4) == {3}


def test_the_split_marks_the_continuation_and_the_count_runs_on():
    lines = [BODY, *NOTE_LINES]
    sizes = [10.5] + [8.52] * len(NOTE_LINES)
    split = split_small_type_block(lines, sizes, body_size=10.5, last_note=6,
                                   indents=[79.4] + HUNG)
    assert split is not None
    assert split.notes[1].startswith(CONTINUES)
    assert definition_numbers(split.notes, 6) == [7, 8]


def test_without_indents_the_split_is_what_it_was():
    lines = [BODY, *NOTE_LINES]
    sizes = [10.5] + [8.52] * len(NOTE_LINES)
    split = split_small_type_block(lines, sizes, body_size=10.5, last_note=6)
    assert not any(ln.startswith(CONTINUES) for ln in split.notes)


def test_the_continued_line_keeps_its_number():
    block = [NOTE_LINES[0], CONTINUES + NOTE_LINES[1], *NOTE_LINES[2:]]
    notes, _leading = _assemble_footnotes(block, definition_start, 6)
    assert sorted(notes) == [7, 8]
    assert "In: MIÖG 10 (1889), pp. 302-25" in notes[7]
    assert CONTINUES not in notes[7]
