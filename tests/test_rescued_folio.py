"""A folio rescued from a running element is a witness, not an appended line.

A running head or footer carrying the page number is stripped as a unit, so the
number has to survive the strip (reflow/running_elements, reflow/outline).
Where the geometry cut the apparatus, the footer sits inside the footnote block
and the rescue happens there.

Four paths rescue such a number, and until stage 6 the weight of the same
rescue depended on which of them found it: the one at the foot of a cut
apparatus stated its case as a witness at half weight, while the three others
wrote the bare number back into the text, where parse_page could not tell it
from a folio the page prints in its own right and gave it full weight. The edge
now decides -- ``printed-head`` at the top, ``printed-footer`` at the foot --
and the geometry decides nothing.

Until stage 5 the rescued number was appended to the page text, which made it
indistinguishable from a folio the page prints in its own right -- and forced a
guard (`8c3254a`): Carlomagno's notes read "N Obra citada. Página NN." page
after page, so the note text passes as a running footer and the number rescued
from it is the *footnote* number. Appended, it landed behind the real folio at
the very foot of the page, and parse_page reads the last line: physical page 39
prints "41" and came out labelled "17", fifteen pages of the volume with it.

The guard could only ever say "not if the body already ends in something that
looks like a label". Now the rescue states its case like every other witness and
the fit decides, which is where a conflict between two readings belongs.
"""

import json

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.verdict import run_verdict
from scriptor.reflow.pagination.witnesses import rescued_observations


def _page(index, label=None):
    return Page(num=-1, body_lines=["Text der Seite."], index=index,
                label_bottom=label)


def test_the_rescue_states_its_reading():
    obs = rescued_observations({7: [("bottom", "146")]})
    assert [(o.pos, o.label, o.source) for o in obs] == [
        (7, "146", "printed-footer")
    ]


def test_the_rescue_weighs_less_than_the_page_itself():
    # It has been through a similarity match that decided the line was furniture
    # -- one step more than a folio the detector reads off the page.
    (o,) = rescued_observations({7: [("bottom", "146")]})
    assert o.weight == 0.5


def test_nothing_is_stated_without_a_rescue():
    assert rescued_observations({7: [("bottom", None)]}) == []
    assert rescued_observations({}) == []


def test_the_edge_decides_which_witness_a_rescue_makes():
    obs = rescued_observations({7: [("top", "146")], 9: [("bottom", "148")]})
    assert [(o.pos, o.source) for o in obs] == [
        (7, "printed-head"), (9, "printed-footer"),
    ]


def test_a_head_rescue_outweighs_a_footer_rescue():
    # The footer rescue reaches into a cut note block by construction and pays
    # for it; the head rescue does not, and the corpus says so -- discounting
    # it lets Lewy's eaten leading digits found a segment of their own
    # (witnesses.HEAD_WEIGHT).
    from scriptor.reflow.pagination.witnesses import (
        FOOTER_WEIGHT, HEAD_WEIGHT, PRINTED_WEIGHT,
    )
    assert FOOTER_WEIGHT < HEAD_WEIGHT
    assert HEAD_WEIGHT == PRINTED_WEIGHT


def test_both_edges_of_one_page_may_speak():
    obs = rescued_observations({7: [("top", "146"), ("bottom", "9")]})
    assert [(o.label, o.source) for o in obs] == [
        ("146", "printed-head"), ("9", "printed-footer"),
    ]


def test_a_rescued_running_head_labels_a_page_and_stays_printed():
    # The archilles contract: every ``printed-*`` source writes label_source
    # "printed". A rescue is lighter, not different in kind.
    pages = [_page(1, "144"), _page(2, "145"), _page(3), _page(4, "147")]
    run_verdict(pages, rescued={3: [("top", "146")]})
    assert [p.label for p in pages] == ["144", "145", "146", "147"]
    assert pages[2].label_source == "printed"


def test_a_rescued_folio_labels_a_page_that_prints_nothing_else():
    pages = [_page(1, "144"), _page(2, "145"), _page(3), _page(4, "147")]
    run_verdict(pages, rescued={3: [("bottom", "146")]})
    assert [p.label for p in pages] == ["144", "145", "146", "147"]
    assert pages[2].label_source == "printed"


def test_the_printed_folio_wins_against_a_rescued_footnote_number():
    # Carlomagno: the page prints "41" at its foot and the apparatus yields
    # "17". Both are stated; the sequence settles it, and no guard is needed.
    pages = [_page(1, "39"), _page(2, "40"), _page(3, "41"), _page(4, "42")]
    run_verdict(pages, rescued={3: [("bottom", "17")]})
    assert [p.label for p in pages] == ["39", "40", "41", "42"]


def test_a_rescued_number_that_fits_nothing_labels_nothing():
    pages = [_page(1, "39"), _page(2, "40"), _page(3), _page(4, "42")]
    run_verdict(pages, rescued={3: [("bottom", "17")]})
    assert pages[2].label == "41"      # the sequence, not the rescue


def test_without_a_rescue_the_verdict_is_unchanged():
    pages = [_page(1, "39"), _page(2, "40"), _page(3), _page(4, "42")]
    run_verdict(pages)
    assert [p.label for p in pages] == ["39", "40", "41", "42"]


# --- a page whose whole content was furniture is still a page -----------------

def test_a_page_that_carried_nothing_but_furniture_keeps_its_place(tmp_path):
    """Josephus and Jesus sets fourteen openings with nothing on them but the
    download banner. While the rescue wrote its number back into the text, that
    number was the page: parse_page saw one line, and the page survived. With
    the number travelling as a witness instead, the page came out empty and was
    dropped -- label, position and all -- so the volume lost fourteen pages it
    numbers.

    Not a blank leaf. The strippers took what was there, and what they took is
    still a statement about the page.
    """
    from scriptor.page import Box, Line, Span, SourcePage, dumps
    from scriptor.reflow.core import main

    def _frag(text, baseline, size=9.0):
        box = Box(30, baseline - 7.0, 30 + 4.5 * len(text), baseline + 2.0)
        return Line(spans=[Span(text, box=box, size=size)], box=box,
                    baseline=baseline)

    # Every line differs from every other: prose repeated verbatim across the
    # volume is itself detected as a running element.
    prose = [
        "Der lange Satz des Brottextes zieht sich weit ueber die Zeile",
        "hin und noch weiter, denn die Seite soll wie gewoehnliche Prosa",
        "aussehen, Zeile um Zeile gleich lang, damit die Modus-Erkennung",
        "sie als Haupttext einordnet und nicht als Vorspann behandelt.",
        "Josephus berichtet vom Aufstand und von den Kaempfen darum.",
        "Die Handschriften der Antiquitates gehen weit auseinander.",
        "Eusebius zitiert die Stelle in seiner Kirchengeschichte auch.",
        "Origenes kannte den Wortlaut offenbar in anderer Fassung noch.",
        "Hieronymus uebersetzt ihn spaeter fuer das lateinische Publikum.",
        "Die Ueberlieferung der Zeugnisse ist im Mittelalter verzweigt.",
        "Photios verzeichnet den Text in seiner Bibliotheke ebenfalls.",
        "Slavische Fassungen weichen an vielen Stellen erheblich ab.",
        "Der Streit um die Echtheit begleitet die Forschung seit langem.",
        "Neuere Arbeiten pruefen den Wortschatz gegen andere Buecher.",
        "Statistische Verfahren geben darauf nur vorlaeufige Antworten.",
        "Ein Urteil verlangt die Zeugen und nicht bloss die Rechnung.",
        "Die Ausgabe von Niese bleibt fuer den Text massgeblich bis heute.",
        "Auch die Randnotizen der Codices sind mehrfach untersucht worden.",
        "Der vorliegende Band sammelt die Belege in einem Anhang neu.",
        "Damit endet der Abschnitt und der naechste beginnt danach.",
        "Ein weiterer Satz schliesst die Seite ordentlich ab hier.",
        "Und noch ein Satz, damit die Seite genug Zeilen bekommt.",
        "Die letzte Zeile dieser Seite sagt nichts Besonderes mehr.",
        "Ein Nachsatz rundet den Gedanken fuer diese Seite endlich ab.",
        "Zum Schluss folgt eine Bemerkung ueber die weitere Anlage.",
        "Der Verfasser dankt den Kollegen fuer manchen Hinweis dazu.",
        "Die Bibliographie verzeichnet die benutzten Ausgaben alle.",
        "Ein Register erschliesst die antiken Quellen nach Buechern.",
    ]
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for i in range(1, 9):
        head = _frag(f"{100 + i}  JOSEPHUS UND DIE ANTIKE HISTORIOGRAPHIE", 20.0)
        # Physical page 4 carries the running head and nothing else.
        body = [] if i == 4 else [
            _frag(prose[(4 * i + k) % len(prose)], 50.0 + k * 12)
            for k in range(4)
        ]
        page = SourcePage(index=i, width=300.0, height=400.0, source="pymupdf",
                          lines=[head, *body])
        (pages_dir / f"{i:08d}.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "buch.md"
    main(str(pages_dir), str(out))

    sidecar = json.loads(
        (tmp_path / "buch.md.pagination.json").read_text(encoding="utf-8"))
    labelled = {p["pos"]: p["label"] for p in sidecar["pages"]}
    assert labelled == {i: str(100 + i) for i in range(1, 9)}
    assert sidecar["pages"][3]["source"] == "printed"

    # The head itself goes, on that page as on every other.
    assert "JOSEPHUS UND DIE ANTIKE" not in out.read_text(encoding="utf-8")
