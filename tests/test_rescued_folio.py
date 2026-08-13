"""A folio rescued from a running footer must not displace a printed one.

A running footer that carries the page number is stripped as a unit, so the
number is put back (reflow/running_elements). Where the geometry cut the
apparatus, the footer sits inside the footnote block and the rescue happens
there -- the number is then appended to the body, because the body no longer
has it.

Carlomagno (Javaloys) breaks that assumption. Its notes read "N Obra citada.
Página NN." on page after page, so the note text itself looks like a running
footer, and the number rescued from it is the *footnote* number. Appending it
put it behind the real folio, which the page prints at its very foot -- and
parse_page reads the last line. Physical page 39 prints "41" and was labelled
"17"; 15 of the volume's pages were labelled with a footnote number this way.
"""
from scriptor.reflow.core import append_rescued_folio


def test_the_folio_is_appended_where_the_body_has_none():
    body = "Ein Absatz Fließtext.\nUnd noch einer."
    assert append_rescued_folio(body, "146").endswith("\n146")


def test_nothing_is_appended_without_a_rescue():
    body = "Ein Absatz Fließtext."
    assert append_rescued_folio(body, None) == body


def test_a_page_that_prints_its_own_folio_keeps_it():
    # The real folio is the last line; the rescued "17" is a footnote number.
    body = "que luego abandonaba cuando la presión militar.\n41"
    assert append_rescued_folio(body, "17") == body


def test_the_check_ignores_trailing_blank_lines():
    body = "Text der Seite.\n41\n\n"
    assert append_rescued_folio(body, "17") == body


def test_a_body_ending_in_prose_still_takes_the_folio():
    body = "Text der Seite, der auf Prosa endet."
    assert append_rescued_folio(body, "41").endswith("\n41")


def test_a_roman_folio_counts_as_one():
    body = "Vorwort des Herausgebers.\nxiv"
    assert append_rescued_folio(body, "9") == body
