"""Paragraph starts from first-line indents (page model).

Zuckerman p. 39: "…blockade of Narbonne ended with its fall.4" fills the whole
printed line, so the short-line heuristic sees no paragraph end — but the next
line starts indented (x0 40.1 against a body edge of 31.3). The indent is the
typographic paragraph signal; carried through as a blank line, the existing
merge logic breaks the paragraph.

Conservative on purpose: the page needs a stable left edge (enough lines on
the mode), the indent must fall inside the band of a first-line indent (a
centred heading or deep quotation is not one), and a line continuing a
hyphenated word can never start a paragraph.
"""

from scriptor.page import Box, Line, Span, SourcePage
from scriptor.reflow.textlines import mark_indent_breaks, reconstruct


def _frag(text, x0, baseline, size=9.0):
    box = Box(x0, baseline - 7.0, x0 + 4.5 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def test_reconstruct_reports_the_left_edge_per_printed_line():
    page = SourcePage(index=1, width=300.0, height=400.0, lines=[
        _frag("Eine Zeile am linken Rand.", 31.3, 50.0),
        _frag("Eine eingerueckte Zeile.", 40.1, 62.0),
    ])
    r = reconstruct(page)
    assert r.indents == [31.3, 40.1]


BODY_EDGE = [
    ("partial victory here. Each one in turn marched against the", 31.3),
    ("Narbonne, the focus of defection and the outpost of Muslim", 31.1),
    ("Gaul. But Charles had to abandon the siege of the fortress,", 31.3),
    ("begun in 737, even though the Saracens failed to relieve", 31.4),
    ("blockade of Narbonne ended with its fall.4", 31.2),
    ("The dependence of Narbonne on support from Spain is evident", 40.1),
    ("from the circumstances of the siege of 737. In order to", 31.3),
]


def test_an_indented_line_gets_a_blank_line_before_it():
    lines = [t for t, _ in BODY_EDGE]
    indents = [x for _, x in BODY_EDGE]
    out = mark_indent_breaks(lines, indents)
    i = out.index("The dependence of Narbonne on support from Spain is evident")
    assert out[i - 1] == ""
    assert len(out) == len(lines) + 1


def test_the_ordinary_scatter_of_the_left_edge_is_not_an_indent():
    lines = [t for t, _ in BODY_EDGE[:5]]
    indents = [x for _, x in BODY_EDGE[:5]]
    assert mark_indent_breaks(lines, indents) == lines


def test_a_centred_or_deeply_indented_line_is_not_a_paragraph_start():
    lines = [t for t, _ in BODY_EDGE[:5]] + ["Ein zentrierter Titel", "und weiter"]
    indents = [x for _, x in BODY_EDGE[:5]] + [120.0, 31.3]
    out = mark_indent_breaks(lines, indents)
    assert "" not in out


def test_a_hyphen_continuation_never_starts_a_paragraph():
    lines = [t for t, _ in BODY_EDGE[:4]] + [
        "the codex of the chronicle covering precisely the mo-",
        "ment of the siege, indented only by damage to the paper.",
    ]
    indents = [x for _, x in BODY_EDGE[:4]] + [31.3, 40.1]
    out = mark_indent_breaks(lines, indents)
    assert "" not in out


def test_a_quotation_on_the_paragraph_indent_opens_one_paragraph_not_one_per_line():
    # McNamara p. 190: the quotation sits 15pt in, where the paragraphs start,
    # and every one of its lines came out a paragraph of its own.
    lines = [t for t, _ in BODY_EDGE[:5]] + [
        "Todd and Dewhurst (1955) have reviewed the role the Double played as",
        "the immortal soul in traditional societies and tribal religions (see",
        "also Hallam, 1980). In these cultures, the Double represents the soul",
    ]
    indents = [x for _, x in BODY_EDGE[:5]] + [46.3, 46.3, 46.4]
    out = mark_indent_breaks(lines, indents)
    assert out.count("") == 1
    assert out[out.index("") + 1].startswith("Todd and Dewhurst")


def test_verse_on_the_indent_keeps_a_paragraph_per_line():
    # Bauer quotes Goethe on the paragraph indent: short lines, each its own.
    lines = [t for t, _ in BODY_EDGE[:5]] + [
        "Meister: Allein du übst die Hand,",
        "Du übst den Blick, nun üb’ auch den Verstand.",
        "Zum Ungemeinem aufzuschwingen:",
    ]
    indents = [x for _, x in BODY_EDGE[:5]] + [40.1, 40.1, 40.1]
    assert mark_indent_breaks(lines, indents).count("") == 3


def test_a_paragraph_of_one_line_does_not_swallow_the_next():
    # Zuckerman: a one-line paragraph, then a list item, both indented.
    lines = [t for t, _ in BODY_EDGE[:5]] + [
        "The clues to this problem are the following:",
        "(1) The taunts of the nations. These are typical of polemical",
    ]
    indents = [x for _, x in BODY_EDGE[:5]] + [40.1, 40.1]
    assert mark_indent_breaks(lines, indents).count("") == 2


def test_a_list_on_the_indent_keeps_one_item_to_a_paragraph():
    # Zuckerman: each item fills its line and closes with a semicolon.
    lines = [t for t, _ in BODY_EDGE[:5]] + [
        "4. to allow Guifred to open a gate in the walls wherever he wishes;",
        "5. to restore to Guifred half of all income derived on land and water,",
    ]
    indents = [x for _, x in BODY_EDGE[:5]] + [40.1, 40.1]
    assert mark_indent_breaks(lines, indents).count("") == 2


def test_without_a_stable_left_edge_nothing_happens():
    lines = ["kurz", "auch kurz", "drittens"]
    assert mark_indent_breaks(lines, [31.0, 40.0, 55.0]) == lines
    assert mark_indent_breaks(lines, [None, None, None]) == lines


def test_full_width_paragraph_ends_break_end_to_end(tmp_path):
    import json
    from scriptor.page import dumps
    from scriptor.reflow.core import main

    prose_a = [
        "Der erste Absatz laeuft ueber mehrere volle Zeilen hinweg und",
        "endet dann buendig auf voller Breite mit seinem letzten Satz.",
    ]
    prose_b = [
        "Der zweite Absatz beginnt eingerueckt, wie es der Setzer wollte,",
        "und laeuft dann am linken Rand weiter, Zeile um Zeile, immerzu,",
        "bis er schliesslich zu seinem eigenen ruhigen Ende gefunden hat.",
    ]
    lines = [_frag("1", 31.3, 20.0)]
    y = 50.0
    for t in prose_a:
        lines.append(_frag(t, 31.3, y)); y += 12.0
    lines.append(_frag(prose_b[0], 40.1, y)); y += 12.0
    for t in prose_b[1:]:
        lines.append(_frag(t, 31.3, y)); y += 12.0
    page = SourcePage(index=1, width=300.0, height=400.0, source="pymupdf", lines=lines)
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "00000001.json").write_text(dumps(page), encoding="utf-8")

    out = tmp_path / "book.txt"
    main(str(pages_dir), str(out))
    text = out.read_text(encoding="utf-8")

    assert "letzten Satz.\n\nDer zweite Absatz beginnt eingerueckt" in text
