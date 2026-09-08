"""The contents searches the raw page, not the page the stripper left behind.

A chapter title is the one thing a volume prints *both* as a heading and as a
running head. The generic stripper removes it as furniture, and it is right to:
by the time the body is read, the head is repetition. But the contents search
runs afterwards and looks for exactly that title -- so on the one page it was
built for, the chapter opening, it finds nothing.

The channel is the whole fix: the same search on the lines as they stood before
``strip_running_elements`` finds the opening, and finds it *there* rather than
on the pages that carry the title as a head, because the search takes the first
hit in reading order and the opening comes first.
"""

import json

from scriptor.page import Box, Line, Span, SourcePage, dumps

TITLE = "Die Uebergabe von Narbonne"

PROSE = [
    "Der lange Satz des Brottextes zieht sich weit ueber die",
    "Zeile hin und noch weiter, denn die Seite soll wie ganz",
    "gewoehnliche Prosa aussehen, Zeile um Zeile gleich lang,",
    "damit die Modus-Erkennung sie als Haupttext einordnet und",
    "nicht als Vorspann. Hier endet der erste lange Absatz.",
]


def _frag(text, baseline, size=9.0, x=30.0):
    box = Box(x, baseline - 7.0, x + 4.5 * len(text), baseline + 2.0)
    return Line(spans=[Span(text, box=box, size=size)], box=box, baseline=baseline)


def _page(index, lines):
    return SourcePage(index=index, width=300.0, height=400.0, source="pymupdf",
                      lines=lines)


def _volume(pages_dir):
    """Six pages, no outline: a contents, an opening, three heads, an end.

    Deliberately without ``outline.json``. Nine of the corpus volumes have no
    outline at all, and those are the volumes this path exists for: with an
    outline the title is already lifted out by ``chapter_headings`` and the
    running heads by ``strip_running_titles``.
    """
    pages_dir.mkdir(parents=True, exist_ok=True)

    contents = _page(1, [
        _frag("Inhalt", 20.0, size=14.0),
        _frag("Vorwort . . . . . . . . . . . . 7", 50.0),
        _frag(f"{TITLE} . . . . . . 36", 64.0),
        _frag("Nachwort . . . . . . . . . . . 60", 78.0),
    ])
    # The chapter opening: the title is the first line of the page, and the
    # page prints its own folio at the foot.
    opening = _page(2, [
        _frag(TITLE, 30.0, size=15.0),
        *[_frag(t, 60.0 + i * 12) for i, t in enumerate(PROSE)],
        _frag("36", 380.0),
    ])
    # Three pages carrying the same title as a running head. Three, because
    # ``detect_running_headers`` needs a group before it calls something
    # furniture.
    heads = [
        _page(i, [
            _frag(TITLE, 20.0),
            _frag(str(35 + i), 20.0, x=250.0),
            *[_frag(t, 60.0 + k * 12) for k, t in enumerate(PROSE)],
        ])
        for i in (3, 4, 5)
    ]
    end = _page(6, [
        *[_frag(t, 60.0 + k * 12) for k, t in enumerate(PROSE)],
        _frag("40", 380.0),
    ])
    for pg in [contents, opening, *heads, end]:
        (pages_dir / f"{pg.index:08d}.json").write_text(dumps(pg), encoding="utf-8")


def _contents_line(err: str) -> str:
    for line in err.splitlines():
        if line.startswith("Contents:"):
            return line
    return ""


def test_the_contents_finds_the_chapter_opening_it_was_built_for(tmp_path, capsys):
    from scriptor.reflow.core import main

    _volume(tmp_path / "pages")
    main(str(tmp_path / "pages"), str(tmp_path / "book.md"))
    err = capsys.readouterr().err

    # The title *is* removed from the body -- that is the stripper doing its
    # job, and the fix does not undo it.
    assert "Running headers removed" in err
    # And the contents still places the opening, with the page it names.
    assert _contents_line(err) == (
        "Contents: 1 further chapter openings (1 of them naming their printed page)"
    )


def test_the_opening_is_found_before_the_pages_that_head_the_title(tmp_path):
    """The find has to land on position 2, not on 3, 4 or 5.

    Reading order is the whole guard here: on the raw channel the title stands
    on four pages, and only the first of them is the chapter.
    """
    from scriptor.reflow.chapters import from_toc
    from scriptor.reflow.core import main

    captured = {}
    real = from_toc

    import scriptor.reflow.chapters as chapters_mod

    def spy(entries, lines_by_pos, toc_positions):
        found = real(entries, lines_by_pos, toc_positions)
        captured["found"] = found
        return found

    chapters_mod.from_toc = spy
    try:
        _volume(tmp_path / "pages")
        main(str(tmp_path / "pages"), str(tmp_path / "book.md"))
    finally:
        chapters_mod.from_toc = real

    assert [(c.pos, c.title, c.printed) for c in captured["found"]] == [
        (2, TITLE, "36")
    ]
