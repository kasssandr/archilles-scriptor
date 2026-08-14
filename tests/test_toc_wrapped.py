"""A contents entry that does not fit on one line.

Between a quarter and a half of the lines in the corpus' contents lists carry
no page number, and the largest group among them is the second half of an entry
that wrapped. Masones sets them indented under their own first line:

    'La Tradición Caballeresca y la Francmasonería'    x=89
    'Escocesa | 36'                                    x=104

Read line by line, the first half is dropped and the second becomes an entry
called "Escocesa" -- one of the "Ungetüme" the user found ("cia | 107",
"vancia | 46", "Hund | 100"). Of that volume's fourteen chapters nine are lost
this way; only the five whose titles fit on one line come through.

What must not be joined is the other kind of line without a number: the chapter
mark. Masones prints 'CAPÍTULO VI' on a line of its own, between the last
section of chapter V (page 90) and the first of chapter VI (page 93). Joining
it to what follows would merge a boundary into an entry.
"""

from scriptor.reflow.core import Page
from scriptor.reflow.toc import parse_toc


def _page(lines):
    return Page(num=-1, body_lines=lines, index=1)


def test_a_wrapped_entry_is_read_as_one():
    page = _page([
        "Los Masones y la Masonería | 19",
        "5. Los Masones en la Edad Media. La Era de la",
        "Piedra | 25",
        "6. Los Gremios de Constructores | 27",
    ])
    titles = [e.title for e in parse_toc([page]).entries]
    assert "Los Masones en la Edad Media. La Era de la Piedra" in titles
    assert "Piedra" not in titles


def test_the_page_number_of_a_wrapped_entry_is_the_one_it_ends_on():
    page = _page(["La Tradición Caballeresca y la Francmasonería",
                  "Escocesa | 36"])
    entries = parse_toc([page]).entries
    assert [(e.title, e.page) for e in entries] == [
        ("La Tradición Caballeresca y la Francmasonería Escocesa", 36)
    ]


def test_a_chapter_mark_is_not_joined_to_the_entry_below_it():
    # 'CAPÍTULO VI' is a boundary, not the first half of the line under it.
    page = _page([
        "4. El regreso de la Caballería | 90",
        "CAPÍTULO VI",
        "La Orden de Estricta Observancia Templaria | 93",
    ])
    titles = [e.title for e in parse_toc([page]).entries]
    assert "La Orden de Estricta Observancia Templaria" in titles
    assert not any(t.startswith("CAPÍTULO") for t in titles)


def test_a_heading_line_is_not_joined_either():
    page = _page(["ÍNDICE", "Nota preliminar | 10", "Introducción | 14"])
    titles = [e.title for e in parse_toc([page]).entries]
    assert titles == ["Nota preliminar", "Introducción"]


def test_only_the_line_directly_above_is_joined():
    # Two orphan lines in a row are not one entry: a contents that wraps twice
    # is rare, and joining a run of them would swallow whatever stands above.
    page = _page(["Erste Waise", "Zweite Waise", "Ein Titel | 12"])
    entries = parse_toc([page]).entries
    assert [e.title for e in entries] == ["Zweite Waise Ein Titel"]


# --- what the typography says about an entry's rank ---------------------------

def test_a_bulleted_entry_ranks_below_an_unbulleted_one():
    """Carlomagno's contents separates its levels by typography alone.

        VERSAL  'I) HEREDERO DE UNA GRAN ESTIRPE FRANCA'   13
                '• La humanidad de Carlos'                  63

    Seven of its eight chapters stand in capitals with a roman number; the
    fifty-one sections carry a bullet. Reading the bullet as rank turns six
    false chapter findings into what they are.
    """
    page = _page([
        "I) HEREDERO DE UNA GRAN ESTIRPE FRANCA | 13",
        "• La dinastía de los Pipínidos | 13",
        "• Nacimiento incógnito | 17",
        "II) EL JOVEN CARLOS | 23",
    ])
    ranks = {e.title.split()[-1]: e.level for e in parse_toc([page]).entries}
    assert ranks["FRANCA"] < ranks["Pipínidos"]      # chapter above section
    assert ranks["CARLOS"] == ranks["FRANCA"]        # both chapters

    # The rank is what a section is good for here: as a label witness it is as
    # sound as a chapter. Carlomagno's "• Carlos consigue la corona" sits on
    # physical page 83 and the contents calls it printed 86 -- which is exactly
    # right at that point in the volume, where the offset has grown to 3.


def test_the_bullet_does_not_survive_into_the_title():
    page = _page(["• La humanidad de Carlos | 63"])
    assert parse_toc([page]).entries[0].title == "La humanidad de Carlos"
