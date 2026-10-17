"""Footnotes set "NN Text" on bare text, where no type size tells them apart.

Without geometry the only convention trusted was "NN)". A volume that sets
its notes "1 Franz Overbeck, …" kept its whole apparatus in the running text
(Taubes, Vom Kult zur Kultur: 2 notes found in 383 pages); only the notes
after the first came apart, wherever a short line happened to end a
paragraph, and the first was glued to the last line of the body.

Two witnesses stand in for the geometry: the count (the number continues the
note read last on the pages before) and the marker (the body above prints
the number glued to a word, the shape a raised number takes once flattened).
"""

from scriptor.reflow.core import parse_page
from scriptor.reflow.footnotes import witnessed_block_start

_BODY = [
    "Die nach dem Ersten Weltkrieg an sich irre werdende liberale Theologie,",
    "die in ihrer Jugendzeit an Overbecks Streitschrift¹ vorbeikam, stand",
    "ratlos vor dem Anspruch dieser Fragmente. Ernst Troeltsch emp-",
]


def test_a_marker_above_opens_the_block():
    page = parse_page("\n".join(_BODY + [
        "1 Franz Overbeck, Über die Christlichkeit unserer heutigen Theologie,",
        "Leipzig 1873.",
        "2 Ebd., S. 200 ff.",
    ]))
    assert page.footnotes == {
        1: "Franz Overbeck, Über die Christlichkeit unserer heutigen Theologie, Leipzig 1873.",
        2: "Ebd., S. 200 ff.",
    }
    assert page.body_lines[-1].endswith("emp-")
    assert "[1]" in page.body_lines[1]


def test_the_count_opens_the_block_without_a_marker():
    lines = ["Ein Satz ohne erkennbaren Marker, der weiterläuft",
             "und hier endet.",
             "13 Die drei Bände sind Der Fürst dieser Welt, München 1983."]
    assert witnessed_block_start(lines, last_read=12) == 2
    assert witnessed_block_start(lines, last_read=40) is None


def test_a_number_nothing_vouches_for_is_prose():
    lines = ["Die Ausgabe umfaßt", "2 Bände und ein Register, die 1953", "erschienen."]
    assert witnessed_block_start(lines) is None


def test_a_number_after_a_space_is_no_marker():
    lines = ["Vgl. Bd. 2 der Ausgabe.", "2 Bände folgten später."]
    assert witnessed_block_start(lines) is None


def test_a_marker_set_on_a_line_of_its_own_opens_nothing():
    # The raised 41 the OCR put on a line of its own; the note comes below.
    lines = ["…den zu durchschauen Aufgabe der Aufklärung bleibt.\"",
             "41",
             "In der als Befreiung verstandenen Geschichte hat auch der Schritt",
             "41 „Zur Konjunktur des Polytheismus“, in: Mythos und Moderne."]
    assert witnessed_block_start(lines, last_read=40) == 3


def test_a_sub_note_marker_opening_a_line_is_prose():
    # Aniane marks sub-notes "92 c)"; the count (91 -> 92) must not take the
    # prose behind it for note 92.
    lines = ["Priestern für die Altäre, hie und da sogar Rechte, wodurch eine um",
             "92 c) ihrerseits den Klöstern und Stiftern machen."]
    assert witnessed_block_start(lines, last_read=91) is None


def test_a_number_alone_before_its_note_text_opens_the_block():
    lines = ["und Theologie und die Dogmata der Kirche als das Produkt der schöpfe-",
             "2",
             "P. Tillich, Systematic Theology, Bd. 1, Chicago 1951, S. vii."]
    assert witnessed_block_start(lines, last_read=1) == 1


def test_stacked_numbers_deal_out_their_notes():
    page = parse_page("\n".join(_BODY + [
        "2",
        "3",
        "Franz Overbeck, Christentum und Kultur. Aus dem Nachlaß hrsg. von",
        "Carl Albrecht Bernoulli, Basel 1919, S. XX.",
        "Eberhard Vischer, Overbeck redivivus, in: Die Christliche Welt, 36,",
        "1922, S. 110 f.",
    ]), last_read=1)
    assert page.footnotes == {
        2: "Franz Overbeck, Christentum und Kultur. Aus dem Nachlaß hrsg. von "
           "Carl Albrecht Bernoulli, Basel 1919, S. XX.",
        3: "Eberhard Vischer, Overbeck redivivus, in: Die Christliche Welt, 36, 1922, S. 110 f.",
    }


def test_stacked_numbers_whose_text_does_not_split_keep_it_on_the_last():
    page = parse_page("\n".join(_BODY + [
        "2",
        "3",
        "Franz Overbeck, Christentum und Kultur, Basel 1919, S. XX, und",
        "Eberhard Vischer, Overbeck redivivus, 1922, S. 110 f.",
    ]), last_read=1)
    assert page.footnotes[2] == ""
    assert page.footnotes[3].startswith("Franz Overbeck") and page.footnotes[3].endswith("S. 110 f.")


def test_a_number_closing_the_parenthesis_above_opens_no_note():
    # "(Röm. 11," / "28)": the citation's verse, not note 28 -- read as one,
    # the rest of the page went into the apparatus.
    page = parse_page("\n".join([
        "Paulus an die christliche Gemeinde in Rom „um euretwillen.\" (Röm. 11,",
        "28)",
        "Mit anderen Worten, Paulus kann das jüdische Schicksal ein Geheim-",
        "nis nennen.",
    ]))
    assert page.footnotes == {}
    assert page.body_lines[1] == "28)"


def test_on_bare_text_a_free_standing_number_is_no_marker():
    # "(Barth, S. 5)" kept its 5; the note without a glued marker is
    # placed at the end of its page later on.
    page = parse_page("\n".join([
        "wobei diese Einführung sich als Ausführung gestalten könnte\"",
        "(Barth, S. 5). Es mag offenbleiben, ob Overbeck das Christentum.",
        "5 Ernst Troeltsch, Rez. Christentum und Kultur, 1920, S. 279 ff.",
    ]), last_read=4)
    assert 5 in page.footnotes
    assert "(Barth, S. 5)." in page.body_lines[1]


def test_on_bare_text_a_number_alone_on_its_line_is_the_marker():
    page = parse_page("\n".join([
        "er hat aber auch nichts zu vollbringen.'",
        "7",
        "Bubers historische Analyse der israelitischen Prophetie.",
        "7 Ebd., S. 64.",
    ]), last_read=6)
    assert page.footnotes == {7: "Ebd., S. 64."}
    assert page.body_lines[1] == "[7]"


def test_a_measured_page_is_not_asked():
    # The geometry answered already: no small type, no block.
    page = parse_page("\n".join(_BODY + ["1 Franz Overbeck, Leipzig 1873."]),
                      geometry_verified=True)
    assert page.footnotes == {}
