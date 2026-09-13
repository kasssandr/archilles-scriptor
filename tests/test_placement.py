"""Where the headings a volume names stand on its pages (Gliederungsmodell B3).

One synthetic volume per case, in the manner of ``eval/golden/synthetic-de``:
the pages are written here, not taken from a copyrighted book, and each one
exercises one rule of Befund §5.2 or §5.4. The wording follows Bauer, whose
defects the rules were measured against.
"""

from scriptor.reflow import placement as pl
from scriptor.reflow.core import Page, reconstruct_body
from scriptor.reflow.heads import HeadCandidates
from scriptor.structure import SchemeRow, SchemeTable


def _page(index: int, label: str | None, *lines: str, mode: str = "main") -> Page:
    page = Page(num=-1, body_lines=list(lines), label=label, mode=mode)
    page.index = index
    return page


def _raw(pages: list[Page]) -> dict[int, list[str]]:
    """The raw channel: the non-empty lines of every page, as core builds it."""
    return {p.index: [ln for ln in p.body_lines if ln.strip()] for p in pages}


def _labels(pages: list[Page], source: str = "printed") -> dict:
    return {p.index: (p.label, source) for p in pages}


def _want(text: str, depth: int = 1, page: str | None = None,
          pos: int | None = None) -> pl.Want:
    return pl.Want(text=text, title=text, depth=depth, page=page, pos=pos)


def _place(pages, wants, *, heads=None, source="printed", skip=()):
    placement = pl.place(wants, _raw(pages), _labels(pages, source), skip=skip)
    applied = pl.apply(pages, placement, heads, skip=skip)
    return placement, applied


def _read(pages, threshold: int = 40):
    """(paragraph, depth) of every block the renderer would write."""
    paragraphs, _fn, _occ, levels = reconstruct_body(pages, threshold)
    return list(zip(paragraphs, levels))


def _prose(n: int) -> list[str]:
    return [f"Zeile {i} des laufenden Textes dieser Seite, gesetzt in voller Breite."
            for i in range(n)]


# ── §5.2, rules 2 and 6: the head line goes, the heading stays ─────────

def test_a_running_head_over_the_page_that_also_prints_the_heading():
    """Bauer p. 23. The wording stands twice: at the head as furniture and in
    the middle of the page as the heading. The stripper deleted both and left
    'kommunika' | 'tive' broken across them."""
    before = _page(22, "22", *_prose(3), "künstlerische und kommunika-")
    page = _page(23, "23",
                 "B. Gang der Darstellung",
                 "tive Aneignungen rechtlich unterschiedlich eingeordnet werden.",
                 *_prose(3),
                 "B. Gang der Darstellung",
                 "Im ersten Kapitel soll der Begriff eingeführt werden.")
    heads = HeadCandidates(24)
    heads.add(22, 0, "B. Gang der Darstellung", "B. Gang der Darstellung",
              from_stripper=False)
    placement, applied = _place([before, page],
                                [_want("B. Gang der Darstellung", 2, page="23")],
                                heads=heads)

    assert [(p.rule, p.in_head) for p in placement.placed] == [(2, False)]
    assert applied.heads_removed == 1
    assert page.body_lines[0].endswith("eingeordnet werden.")
    blocks = _read([before, page])
    assert ("B. Gang der Darstellung", 2) in blocks
    assert any("kommunikative" in text for text, _d in blocks)  # the word is whole
    assert not any(text.startswith("B. Gang der Darstellung") and depth == 0
                   for text, depth in blocks)


def test_a_chapter_opening_at_the_top_carries_no_running_head():
    """Bauer p. 24. The same words at the head of a page, and here they are
    the heading: no other occurrence, and the entry names this page."""
    page = _page(24, "24",
                 "Erstes Kapitel: Die bildliche Aneignung",
                 "Aneignung ist ein Begriff mit mehreren Bedeutungen.",
                 *_prose(3))
    heads = HeadCandidates(25)
    heads.add(23, 0, "Erstes Kapitel: Die bildliche Aneignung",
              "Erstes Kapitel: Die bildliche Aneignung", from_stripper=False)
    placement, applied = _place(
        [page], [_want("Erstes Kapitel: Die bildliche Aneignung", 1, page="24")],
        heads=heads)

    assert [(p.rule, p.in_head) for p in placement.placed] == [(3, True)]
    assert applied.heads_removed == 0
    assert _read([page])[0] == ("Erstes Kapitel: Die bildliche Aneignung", 1)


def test_one_further_occurrence_at_a_head_is_enough_to_be_furniture():
    """No threshold of three repetitions. Once the volume itself names the
    title, a second occurrence in a head region is the running head of the
    page after the opening -- the generic stripper needs three and lets this
    one through (Bauer p. 21)."""
    opening = _page(20, "20", "IV. Begriff des Bildlichen", *_prose(3))
    after = _page(21, "21", "IV. Begriff des Bildlichen", *_prose(4))
    heads = HeadCandidates(22)
    for index in (19, 20):
        heads.add(index, 0, "IV. Begriff des Bildlichen",
                  "IV. Begriff des Bildlichen", from_stripper=False)
    placement, applied = _place([opening, after],
                                [_want("IV. Begriff des Bildlichen", 3, page="20")],
                                heads=heads)

    assert [p.pos for p in placement.placed] == [20]
    assert applied.heads_removed == 1
    assert after.body_lines[0].startswith("Zeile 0")


def test_a_head_line_whose_title_was_never_placed_stays():
    """Rule 6 is about every *further* occurrence. Where nothing was placed
    there is no first one, and taking the line out would remove words the
    volume prints on no evidence at all."""
    page = _page(30, "30", "V. Ein Titel ohne Fundstelle", *_prose(3))
    heads = HeadCandidates(31)
    heads.add(29, 0, "V. Ein Titel ohne Fundstelle", "V. Ein Titel ohne Fundstelle",
              from_stripper=False)
    placement, applied = _place([page], [_want("Ein ganz anderer Titel", 2,
                                               page="30")], heads=heads)

    assert placement.unplaced and applied.heads_removed == 0
    assert page.body_lines[0] == "V. Ein Titel ohne Fundstelle"


# ── §5.2, rule 8 and §2.4: a heading owns whole lines ──────────────────

def test_a_title_broken_across_two_lines_becomes_one_heading():
    page = _page(40, "40", *_prose(2),
                 "I. Die Antike: Der Künstler im Dialog mit der",
                 "Vorlage",
                 "Platon beschreibt die Nachahmung als Abbild.")
    title = "I. Die Antike: Der Künstler im Dialog mit der Vorlage"
    placement, _applied = _place([page], [_want(title, 3, page="40")])

    assert [p.n_lines for p in placement.placed] == [2]
    assert (title, 3) in _read([page])


def test_a_title_the_reflow_broke_into_two_paragraphs_is_still_one_heading():
    """G3's new class: the printed line break became a paragraph break, because
    the second line is indented and mark_indent_breaks reads an indent as one.
    The heading takes its lines across the blank (Briefing §8.5)."""
    page = _page(41, "41", *_prose(2),
                 "I. Die Antike: Der Künstler im Dialog mit der",
                 "",
                 "Vorlage",
                 "1. Platon und die Nachahmung")
    title = "I. Die Antike: Der Künstler im Dialog mit der Vorlage"
    _placement, _applied = _place(
        [page], [_want(title, 3, page="41"),
                 _want("1. Platon und die Nachahmung", 4, page="41")])

    assert [b for b in _read([page]) if b[1]] == [
        (title, 3), ("1. Platon und die Nachahmung", 4)]


def test_three_levels_glued_into_one_paragraph_come_apart():
    """Bauer §2.2: the page sets them on their own lines and the reflow reads
    them as the opening of the paragraph that follows."""
    page = _page(24, "24",
                 "A. Bildliche Aneignung – eine Definition",
                 "I. Aneignung als Rechtsbegriff",
                 "1. Aneignung als allgemeinsprachlicher Begriff",
                 "Der Begriff der Aneignung findet sich im Gesetz an mehreren Stellen.")
    wants = [_want("A. Bildliche Aneignung – eine Definition", 2, page="24"),
             _want("I. Aneignung als Rechtsbegriff", 3, page="24"),
             _want("1. Aneignung als allgemeinsprachlicher Begriff", 4, page="24")]
    _place([page], wants)

    blocks = _read([page])
    assert [(text, depth) for text, depth in blocks if depth] == [
        ("A. Bildliche Aneignung – eine Definition", 2),
        ("I. Aneignung als Rechtsbegriff", 3),
        ("1. Aneignung als allgemeinsprachlicher Begriff", 4),
    ]
    assert blocks[-1][0].endswith("an mehreren Stellen.")


# ── §5.2, rules 4, 5, 7 and §5.9: what the page cannot confirm ─────────

def test_a_contents_page_number_from_another_edition_falls_back_to_the_first():
    """The entry names page 70, the edition breaks elsewhere. Rules 2 and 3
    find nothing and the old rule -- first occurrence in reading order -- is
    the right fallback for exactly this class."""
    page = _page(64, "64", *_prose(2), "III. Der Umbruch", *_prose(2))
    placement, _applied = _place([page], [_want("III. Der Umbruch", 3, page="70")])

    assert [(p.pos, p.rule) for p in placement.placed] == [(64, 4)]


def test_a_label_the_contents_supplied_does_not_confirm_the_page():
    """Befund §5.9, question 4: that would be the contents agreeing with
    itself. The entry is placed by reading order instead."""
    named = _page(50, "50", *_prose(2), "II. Ein Abschnitt", *_prose(2))
    placement, _applied = _place([named], [_want("II. Ein Abschnitt", 3, page="50")],
                                 source="toc")

    assert [p.rule for p in placement.placed] == [4]


def test_an_entry_found_on_no_page_is_named_and_nothing_is_inserted():
    page = _page(60, "60", *_prose(3))
    placement, applied = _place([page], [_want("VII. Ein verlorener Titel", 3,
                                               page="60")])

    assert [w.text for w in placement.unplaced] == ["VII. Ein verlorener Titel"]
    assert applied.marked == 0
    assert page.body_lines == _prose(3)


def test_a_find_against_the_order_of_the_list_is_rejected():
    """The volume prints its own title on the title page as well, and rule 4
    has nothing better to go by. Order catches it (rule 7)."""
    pages = [_page(2, "2", "Der dritte Abschnitt", *_prose(2)),
             _page(10, "10", *_prose(2), "Der erste Abschnitt", *_prose(2)),
             _page(20, "20", *_prose(2), "Der zweite Abschnitt", *_prose(2)),
             _page(30, "30", *_prose(2), "Der dritte Abschnitt", *_prose(2)),
             _page(40, "40", *_prose(2), "Der vierte Abschnitt", *_prose(2))]
    # The third entry names the page the title page carries: a volume prints
    # its part titles twice, and the contents can only name one of them.
    wants = [_want("Der erste Abschnitt", 1, page="10"),
             _want("Der zweite Abschnitt", 1, page="20"),
             _want("Der dritte Abschnitt", 1, page="2"),
             _want("Der vierte Abschnitt", 1, page="40")]
    placement, _applied = _place(pages, wants)

    assert [p.pos for p in placement.placed] == [10, 20, 40]
    assert [(w.text, why) for w, why in placement.rejected] == [
        ("Der dritte Abschnitt", "out of the order its list is written in")]


# ── §5.4: the numbered lines no entry placed ──────────────────────────

def _table(*rows: tuple[str, int]) -> SchemeTable:
    return SchemeTable([SchemeRow(scheme, depth, 3) for scheme, depth in rows])


def test_a_numbered_line_of_a_scheme_the_contents_leads_is_not_a_heading():
    """Bauer's eleven theses are numbered like the fourth level of its tree,
    and the contents names none of them."""
    page = _page(317, "317",
                 "Die Untersuchung hat die Aneignung als Sammelbegriff entwickelt.",
                 "2. Die Aneignung von Bildern ist eine kommunikative Praxis.")
    result = pl.judge_numbering([page], _table(("arabic", 4)), roman=False)

    assert [r["text"] for r in result.refused] == [
        "2. Die Aneignung von Bildern ist eine kommunikative Praxis."]
    # One paragraph, no heading: a refused line does not even break the text.
    assert [depth for _text, depth in _read([page])] == [0]


def test_a_run_in_a_scheme_the_contents_never_leads_is_the_level_below_it():
    """'aa)' under a contents that leads 'a)'. The run, the short line and the
    finished sentence before it are all three needed: without them G6 found
    nineteen volumes' worth of footnotes and enumerations."""
    page = _page(150, "150",
                 "Der Adressatenkreis ist nach der Rechtsprechung zu bestimmen.",
                 "aa) Unbestimmte Zahl",
                 "Frame-Links sind allen Internetnutzern zugänglich und damit offen.",
                 "bb) Recht viele Personen",
                 "Die Zahl der Adressaten muss erheblich sein, sagt der Gerichtshof.")
    table = _table(("letter-lower-paren", 5))
    result = pl.judge_numbering([page], table, roman=False)

    assert [r["text"] for r in result.promoted] == [
        "aa) Unbestimmte Zahl", "bb) Recht viele Personen"]
    assert [depth for _text, depth in _read([page], threshold=30)] == [0, 6, 0, 6, 0]


def test_a_single_numbered_line_of_an_unknown_scheme_is_not_promoted():
    page = _page(151, "151",
                 "Der Adressatenkreis ist nach der Rechtsprechung zu bestimmen.",
                 "aa) Unbestimmte Zahl",
                 "Frame-Links sind allen Internetnutzern zugänglich und damit offen.")
    result = pl.judge_numbering([page], _table(("letter-lower-paren", 5)),
                                roman=False)

    assert result.promoted == []


def test_a_numbered_line_continuing_a_sentence_is_not_promoted():
    """Bauer's thesis 2 follows 'entwickelt.' -- but a line under a sentence
    that has not ended is its continuation, whatever it is numbered."""
    page = _page(152, "152",
                 "Der Adressatenkreis ist nach der Rechtsprechung zu bestimmen und",
                 "aa) Unbestimmte Zahl",
                 "bb) Recht viele Personen")
    result = pl.judge_numbering([page], _table(("letter-lower-paren", 5)),
                                roman=False)

    assert [r["text"] for r in result.promoted] == ["bb) Recht viele Personen"] or \
        result.promoted == []


def test_a_long_line_is_not_a_heading_however_it_is_numbered():
    """G6: short for its page, measured against the page's own lines. Without
    it the rule found footnotes and literature lists."""
    page = _page(153, "153", *_prose(2),
                 "aa) Ein Absatz, der mit einem Bezeichner beginnt und dann über "
                 "die ganze Breite der Seite weiterläuft, ist keine Überschrift.",
                 "bb) Und dieser hier ebenso wenig, denn er füllt die Zeile aus "
                 "und sagt einen ganzen Satz.")
    result = pl.judge_numbering([page], _table(("letter-lower-paren", 5)),
                                roman=False)

    assert result.promoted == []


def test_a_run_of_the_lowest_level_is_not_broken_by_a_page_end():
    """La masonería sets seventeen of them over thirty-one pages (G6). What
    ends a run is a heading, not a leaf of paper."""
    first = _page(80, "80", *_prose(3), "1. EL MITO DEL ANTICLERICALISMO")
    second = _page(81, "81", *_prose(3), "2. LA LEYENDA NEGRA")
    result = pl.judge_numbering([first, second], _table(("roman-upper", 1)),
                                roman=True)

    assert [r["text"] for r in result.promoted] == [
        "1. EL MITO DEL ANTICLERICALISMO", "2. LA LEYENDA NEGRA"]
