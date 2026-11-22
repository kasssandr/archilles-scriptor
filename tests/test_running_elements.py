"""Tests for running-element removal.

Focus: when removing a recurring running head, a page number embedded in it
("146 WILHELM HEIL") must survive the strip. Previously the whole line
including the number was deleted (Braunfels case, open follow-ups #1); then the
bare number was written back into the text, which made it indistinguishable
from a folio the page prints in its own right and gave it full printed weight
wherever the geometry happened not to cut the apparatus. It now leaves the
strippers as a *rescued* number and states its case to the consensus like every
other witness (reflow/pagination/witnesses.rescued_observations).
"""

import random

from scriptor.reflow.rescued import RescuedFolios
from scriptor.reflow.running_elements import (
    strip_running_elements,
    detect_running_footers,
    remove_running_footers_from_blocks,
    remove_running_headers,
    detect_running_headers,
    head_region,
    _extract_edge_page_number,
    _strings_are_similar,
)
from scriptor.reflow.core import parse_page


# --- head_region ---------------------------------------------------------------

def test_head_region_is_three_lines_with_words_and_the_folios_among_them():
    page = "\n".join(["17", "", "Eine Kopfzeile", "Zweite Zeile", "Dritte Zeile",
                      "Vierte Zeile"])
    assert head_region(page) == [(0, "17"), (2, "Eine Kopfzeile"),
                                 (3, "Zweite Zeile"), (4, "Dritte Zeile")]


def test_the_detector_reaches_a_head_below_a_folio_line():
    # Folio on a line of its own, two lines of furniture, then the running
    # head: the third line with words, the fourth line of the page.
    pages = [
        "\n".join([str(30 + i), "Ein Verlagsband zum Herunterladen",
                   f"Heruntergeladen am {i + 1}. Mai von einer Bibliothek",
                   "Die Ordnung der Dinge im Text",
                   f"Ein eigener Satz des Textes auf Seite {i} mit Inhalt."])
        for i in range(4)
    ]
    assert "Die Ordnung der Dinge im Text" in detect_running_headers(pages)


# --- _extract_edge_page_number ------------------------------------------------

def test_extract_leading_edge_number():
    assert _extract_edge_page_number("146 WILHELM HEIL") == "146"


def test_extract_trailing_edge_number():
    assert _extract_edge_page_number("WILHELM HEIL 147") == "147"


def test_extract_none_without_edge_number():
    assert _extract_edge_page_number("WILHELM HEIL") is None
    # A number in the middle is not a page number.
    assert _extract_edge_page_number("BAND 2 STAUFER") is None


# --- strip_running_elements: header with an embedded page number ---------------

# Content-wise clearly distinct sentences: body lines must not resemble each
# other (SequenceMatcher ≥ 0.85 would otherwise group them as a running element).
_DISTINCT = [
    "Karl der Große gründete viele Klöster im fränkischen Reich.",
    "Die Reichenau war ein Zentrum mittelalterlicher Buchmalerei.",
    "Benedikt von Aniane reformierte das abendländische Mönchtum.",
    "Ludwig der Fromme förderte die klösterliche Erneuerung sehr.",
    "Skriptorien kopierten kostbare Handschriften über viele Jahre.",
    "Die Abtei Gellone pflegte eine besondere liturgische Tradition.",
    "Pippin stärkte das Bündnis mit dem römischen Papsttum deutlich.",
    "Alkuin von York prägte die karolingische Bildungsreform stark.",
    "Mönche bewahrten antikes Wissen in stillen Bibliotheken auf.",
    "Urkunden regelten Besitz und Rechte der Klöster ganz genau.",
    "Die Hofschule zu Aachen versammelte die Gelehrten der Epoche.",
    "Reliquien zogen zahlreiche Pilger in fränkische Heiligtümer.",
]


def _heil_pages(nums, *, trailing=False):
    # Body differs in content per page, so only the running head is
    # recognised as the recurring running element.
    pages = []
    for i, n in enumerate(nums):
        b1 = _DISTINCT[(2 * i) % len(_DISTINCT)]
        b2 = _DISTINCT[(2 * i + 1) % len(_DISTINCT)]
        head = f"WILHELM HEIL {n}" if trailing else f"{n} WILHELM HEIL"
        pages.append(f"{head}\n{b1}\n{b2}")
    return pages


def test_strip_rescues_a_leading_page_number():
    nums = (146, 148, 150, 152)
    rescued = RescuedFolios(len(nums))
    cleaned, headers, _ = strip_running_elements(_heil_pages(nums), rescued)
    assert headers, "wiederkehrender Kolumnentitel muss erkannt werden"
    assert rescued.by_position() == {
        i: [("top", str(n))] for i, n in enumerate(nums, start=1)
    }
    for page in cleaned:
        assert "WILHELM HEIL" not in page          # title gone
        assert not any(c.isdigit() for c in page)  # and the number with it


def test_strip_rescues_a_trailing_page_number():
    nums = (147, 149, 151)
    rescued = RescuedFolios(len(nums))
    cleaned, headers, _ = strip_running_elements(
        _heil_pages(nums, trailing=True), rescued)
    assert headers
    assert rescued.by_position() == {
        i: [("top", str(n))] for i, n in enumerate(nums, start=1)
    }
    for page in cleaned:
        assert "WILHELM HEIL" not in page
        assert not any(c.isdigit() for c in page)


def test_header_without_number_fully_removed():
    # Regression: a header without a number is still removed completely,
    # and no number is invented; the body is preserved.
    nums = (1, 2, 3, 4)
    pages = []
    for i in nums:
        b1 = _DISTINCT[(2 * (i - 1)) % len(_DISTINCT)]
        b2 = _DISTINCT[(2 * (i - 1) + 1) % len(_DISTINCT)]
        pages.append(f"WILHELM HEIL\n{b1}\n{b2}")
    rescued = RescuedFolios(len(pages))
    cleaned, headers, _ = strip_running_elements(pages, rescued)
    assert headers
    assert rescued.by_position() == {}
    for page in cleaned:
        assert "WILHELM HEIL" not in page
        assert not any(c.isdigit() for c in page)
        assert page.strip()  # body survives


def test_two_running_heads_on_one_page_are_two_statements():
    # Josephus and Jesus (OUP) heads every page twice: a download banner ending
    # in the year of the download, and the chapter's running head ending in the
    # folio. Keeping only the first rescue threw the folio away and left "2025"
    # to speak for the page -- on 330 pages, which cost the volume its
    # catalogue and 26 labels.
    banner = "Downloaded from https://academic.oup.com/book/60034 by guest 2025"
    pages = []
    for i, n in enumerate(range(110, 118)):
        body = _DISTINCT[(2 * i) % len(_DISTINCT)]
        pages.append(f"{banner}\nAUTHENTICITY of the Testimonium  {n}\n{body}")
    rescued = RescuedFolios(len(pages))
    cleaned, headers, _ = strip_running_elements(pages, rescued)
    assert len(headers) == 2, "beide Kopfzeilen sind wiederkehrende Elemente"
    assert rescued.by_position()[1] == [("top", "2025"), ("top", "110")]
    for page in cleaned:
        assert "Downloaded" not in page and "AUTHENTICITY" not in page


# --- End-to-end: the rescue does not become a folio the page "prints" ---------

def test_the_rescued_number_never_reaches_parse_page_as_a_label():
    # The point of the change: parse_page reads what the page printed, and this
    # page printed the number inside furniture. It reaches the consensus as a
    # rescue instead, with a weight that says so.
    nums = (146, 148, 150)
    rescued = RescuedFolios(len(nums))
    cleaned, _, _ = strip_running_elements(_heil_pages(nums), rescued)
    pg = parse_page(cleaned[0])
    assert pg.label_top is None
    assert pg.label_bottom is None
    assert rescued.by_position()[1] == [("top", "146")]


# --- Footer with an embedded page number (consistency) -------------------------

def test_strip_preserves_footer_number():
    nums = tuple(range(10, 16))
    # The footer sits after several content-distinct body lines, so it isn't
    # already recognised as a header within the first 3 lines.
    pages = []
    for i, n in enumerate(nums):
        body = "\n".join(_DISTINCT[(2 * i + k) % len(_DISTINCT)] for k in range(4))
        pages.append(f"{body}\nQUELLENBAND ZWEI {n}")
    rescued = RescuedFolios(len(pages))
    cleaned, _, footers = strip_running_elements(pages, rescued, footer_min=3)
    assert footers, "wiederkehrender Fußtitel muss erkannt werden"
    assert rescued.by_position() == {
        i: [("bottom", str(n))] for i, n in enumerate(nums, start=1)
    }
    for page in cleaned:
        assert "QUELLENBAND" not in page
        assert not any(c.isdigit() for c in page)


# --- A running element quoted inside a longer real line ------------------------

# Regression (EXCITE 35056, p. 4): the publisher's name is the running footer,
# and a footnote cites that same publisher. The note line contains the footer
# verbatim but is much longer — it is body text, not a running element, and
# must survive. Silent loss of a text line is worse than a visible error.
_DIE_FOOTER = "Deutsches Institut für Entwicklungspolitik"
_DIE_NOTE = (
    "Bonn: Deutsches Institut für Entwicklungspolitik (Discussion Paper 7/2006)."
)


def test_similarity_rejects_a_short_substring_of_a_long_line():
    # The footer covers barely half the note line; SequenceMatcher puts them at
    # 0.72, well under the 0.85 threshold. Only the substring shortcut said yes.
    assert not _strings_are_similar(_DIE_NOTE, _DIE_FOOTER)


def test_similarity_still_accepts_a_line_that_is_essentially_the_element():
    # The shortcut's legitimate case must keep working: trailing punctuation or
    # a stray word around an otherwise identical running element.
    assert _strings_are_similar(_DIE_FOOTER + ".", _DIE_FOOTER)


def test_footer_quoted_in_a_footnote_survives():
    # Ordered as in the source: the citing note sits on an early page, the
    # plain running footer carries the rest of the volume.
    tail = "\n".join(_DISTINCT[k] for k in range(3))
    pages = [f"{tail}\n{_DIE_NOTE}"]
    for i in range(1, 7):
        body = "\n".join(_DISTINCT[(2 * i + k) % len(_DISTINCT)] for k in range(3))
        pages.append(f"{body}\n{_DIE_FOOTER}")

    cleaned, _, footers = strip_running_elements(pages, footer_min=3)
    assert footers, "wiederkehrender Fußtitel muss erkannt werden"
    for page in cleaned[1:]:
        assert _DIE_FOOTER not in page  # the real running footer goes
    assert _DIE_NOTE in cleaned[0]  # the footnote citing it stays


# --- the footer inside a cut apparatus ----------------------------------------
# Where the page geometry cut a footnote block, the running footer no longer
# sits at the foot of the body: it sits in the last line of the block, together
# with the folio. SSOAR 35056 is the case -- "36    Deutsches Institut für
# Entwicklungspolitik" -- and there the detector saw the line on too few pages
# to recognise it at all, while the block carried it straight into the notes.

def _split_pages(n=4):
    """n pages, each already divided into body text and a cut apparatus.

    Every line differs from every other, notes included: text that merely
    varies a number ("1 Vgl. Beleg 1." against "2 Vgl. Beleg 2.") is grouped
    as one recurring element and would be detected as the footer itself.
    """
    bodies, blocks = [], []
    for i in range(n):
        bodies.append(f"{_DISTINCT[2 * i]}\n{_DISTINCT[2 * i + 1]}")
        blocks.append([f"{i + 1} {_DISTINCT[2 * n + i]}", f"{i + 10}    {_DIE_FOOTER}"])
    return bodies, blocks


def test_footer_hidden_in_the_apparatus_is_detected():
    bodies, blocks = _split_pages()
    assert not detect_running_footers(bodies, min_occurrences=3), (
        "ohne die Blöcke steht der Fußtitel auf keiner Seite am Fuß des Textes"
    )
    _, _, footers = strip_running_elements(
        bodies, footer_min=3, foot_blocks=blocks)
    assert any(_strings_are_similar(f, _DIE_FOOTER) for f in footers)


def test_footer_leaves_the_apparatus_and_hands_back_its_folio():
    bodies, blocks = _split_pages()
    _, _, footers = strip_running_elements(
        bodies, footer_min=3, foot_blocks=blocks)
    rescued = RescuedFolios(len(blocks))
    cleaned = remove_running_footers_from_blocks(blocks, footers, rescued)
    assert cleaned[0] == [f"1 {_DISTINCT[8]}"], "der Fußtitel gehört nicht zu Note 1"
    assert rescued.by_position()[1] == [("bottom", "10")], (
        "die Folio darf nicht mit dem Fußtitel verschwinden"
    )


def test_a_block_without_the_footer_is_left_alone():
    blocks = [["1 Vgl. Beleg 1.", "und eine Fortsetzungszeile dazu."]]
    rescued = RescuedFolios(len(blocks))
    cleaned = remove_running_footers_from_blocks(blocks, [_DIE_FOOTER], rescued)
    assert cleaned[0] == blocks[0]
    assert rescued.by_position() == {}


# --- a chapter footer whose folio changes edge (Wolf) --------------------------

_WOLF_FOOTER = "# 8 Waren die Landgrafen von Thüringen"


def _wolf_pages(feet: dict[int, str], n: int = 70) -> list[str]:
    """n pages with bodies unlike one another, footed where ``feet`` says."""
    return [f"Seite {i} spricht von Urkunde {i * 7} und Zeuge {i * 13}.\n"
            f"Dazu gehört Beleg {i * 31} aus dem Jahr {1000 + i}."
            + (f"\n{feet[i]}" if i in feet else "")
            for i in range(n)]


def test_a_chapter_footer_is_found_where_its_opening_page_numbers_it_trailing():
    # The opening page, a recto, numbers the wording at its end; the versos at
    # their start. Each folio is its page plus the same offset.
    feet = {1: f"{_WOLF_FOOTER} 381"}
    feet.update({i: f"{380 + i} {_WOLF_FOOTER}" for i in range(2, 14, 2)})
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert any(_strings_are_similar(f, _WOLF_FOOTER) for f in footers), (
        "ein Mitglied mit der Folio am anderen Rand darf die Gruppe nicht kippen"
    )


def test_a_plate_without_its_number_does_not_sink_the_footer():
    # On a plate the folio stands on a line of its own; the wording is bare.
    feet = {i: f"{380 + i} {_WOLF_FOOTER}" for i in range(2, 14, 2)}
    feet[8] = _WOLF_FOOTER
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert any(_strings_are_similar(f, _WOLF_FOOTER) for f in footers)


def test_bare_wordings_must_not_outnumber_the_counted_ones():
    feet = {i: _WOLF_FOOTER for i in range(2, 14, 2)}
    feet[2], feet[4] = f"382 {_WOLF_FOOTER}", f"384 {_WOLF_FOOTER}"
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert not any(_strings_are_similar(f, _WOLF_FOOTER) for f in footers)


def test_numbers_at_changing_edges_must_still_count_the_pages():
    # Same wording, edges changing, but the number at the trailing edge is off
    # by one: no shared offset, so nothing here counts the pages.
    feet = {1: f"{_WOLF_FOOTER} 382"}
    feet.update({i: f"{380 + i} {_WOLF_FOOTER}" for i in range(2, 14, 2)})
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert not any(_strings_are_similar(f, _WOLF_FOOTER) for f in footers)


# --- speed: the cheap bounds must not change a single answer ------------------

def test_the_cheap_bounds_never_change_an_answer():
    """``real_quick_ratio`` and ``quick_ratio`` are upper bounds on ``ratio``.

    Skipping the expensive comparison where a bound already falls below the
    threshold is therefore free of consequence -- but only if that is actually
    true of every pair, including the shortcut cases the function handles before
    it ever reaches SequenceMatcher. Checked against the plain definition over
    pairs built to sit on both sides of the threshold and on it.
    """
    from difflib import SequenceMatcher

    base = [
        "The Oxford Handbook of the Hellenistic and Roman Near East",
        "Rubina Raja (ed.)",
        "Bibliography",
        "Google Scholar Google Preview WorldCat COPAC",
        "146 WILHELM HEIL",
        "Deutsches Institut fuer Entwicklungspolitik",
        "Bonn: Deutsches Institut fuer Entwicklungspolitik (Discussion Paper).",
        "some ordinary line of body text that begins a page mid-sentence",
        "some ordinary line of body text that begins a page mid-sentenc",
        "",
        "a",
    ]
    pairs = [(a, b) for a in base for b in base]
    for a, b in pairs:
        plain = bool(a) and bool(b) and (
            a == b
            or (b in a and len(b) >= 0.85 * len(a))
            or SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.85
        )
        assert _strings_are_similar(a, b) is plain, (a, b)


def test_grouping_a_volume_that_has_no_running_head_stays_fast():
    """A volume whose pages start mid-sentence puts every first line in a group
    of its own, so the grouping loop grows quadratically -- and each comparison
    used to run a full SequenceMatcher. The Oxford Handbook (911 pages) spent
    98.5 % of an 18-minute run in here.

    The bound is generous: the point is to catch the return of an O(n^2) run of
    full comparisons, not to pin a machine's speed.
    """
    import random
    import time

    # The lines have to differ in their *word material*, not just in a number:
    # near-identical lines all land in one group and never exercise the loop.
    random.seed(7)
    words = (
        "Antiochus Seleucid tetradrachm Phoenician autonomy coinage Ptolemaic "
        "inscription sanctuary excavation Hellenistic Palmyra Nabataean temple "
        "amphora necropolis basalt limestone epigraphy chronology stratigraphy"
    ).split()
    pages = [" ".join(random.choice(words) for _ in range(random.randint(7, 11)))
             for _ in range(400)]

    t0 = time.perf_counter()
    assert detect_running_headers(pages) == []
    elapsed = time.perf_counter() - t0
    # Measured on this input: 16.2s before the cheap bounds went in front of the
    # full comparison, 3.3s after. The bound sits between the two rather than
    # close to the new value -- the point is to catch the return of an O(n^2)
    # run of full comparisons, not to pin a machine's speed.
    assert elapsed < 8.0, f"grouping took {elapsed:.1f}s"


# --- The page that opens a running head's run keeps its title ------------------
#
# Taubes, *Vom Kult zur Kultur* (1996): the essay title is the recto running
# head, and the essay's first page prints it at the top without a folio. With
# no readable contents to recognise it by, the stripper deleted all of them.

from scriptor.reflow.headings import MARK

_HEAD = "Die Kloester des Westens"


def _run(first, *, before="Damit endet der Abschnitt.", n=4):
    """A page before the section, then the section: its opening page starts
    with ``first`` (lines), every later page with folio and running head."""
    # A full page of text: a short one would read as a section's end.
    pages = ["\n".join([*_DISTINCT[4:11], before])]
    pages.append("\n".join([*first, _DISTINCT[1], _DISTINCT[2]]))
    for i in range(n - 1):
        pages.append(f"{20 + i}\n{_HEAD}\n{_DISTINCT[3 + i]}")
    return pages


def _strip(pages):
    kept: list = []
    cleaned = remove_running_headers(
        pages, [_HEAD], RescuedFolios(len(pages)), kept=kept)
    return cleaned, kept


def test_the_opening_page_keeps_its_title_marked():
    cleaned, kept = _strip(_run([_HEAD]))
    assert cleaned[1].split("\n")[0] == MARK + _HEAD
    assert kept == [(1, _HEAD)]
    assert all(_HEAD not in page for page in cleaned[2:])


def test_a_title_set_over_two_lines_is_one_heading():
    cleaned, kept = _strip(_run(["Die Kloester", "des Westens"]))
    assert cleaned[1].split("\n")[0] == MARK + "Die Kloester des Westens"
    assert "des Westens" not in cleaned[1].split("\n")[1]
    assert kept == [(1, "Die Kloester des Westens")]


def _openings(*titles):
    """Pages that each open with ``title`` (lines) over two lines of text, and
    the openings table naming the first line of each as the head's span."""
    pages = ["\n".join([*t, _DISTINCT[1], _DISTINCT[2]]) for t in titles]
    return pages, {i: {0: [0]} for i in range(len(pages))}


def test_an_open_title_runs_on_to_the_line_that_closes_it():
    # The running head shortens the title ("… u. s. w."), so only its first
    # line reads as the head; the volume closes every other title.
    from scriptor.reflow.running_elements import _close_open_titles

    pages, openings = _openings(
        ["Erster Abschnitt."], ["Zweiter Abschnitt."],
        ["Die drei Diplome samt", "ihrer Erneuerung durch den", "Kaiser."])
    _close_open_titles(openings, pages)
    assert openings[2] == {0: [0, 1, 2]}
    assert openings[0] == {0: [0]}


def test_in_a_volume_whose_titles_do_not_close_nothing_runs_on():
    from scriptor.reflow.running_elements import _close_open_titles

    pages, openings = _openings(
        ["Erster Abschnitt"], ["Zweiter Abschnitt"],
        ["Die drei Diplome samt", "ihrer Erneuerung durch den", "Kaiser."])
    _close_open_titles(openings, pages)
    assert openings[2] == {0: [0]}


def test_an_open_title_that_closes_nowhere_near_stays_as_it_was():
    from scriptor.reflow.running_elements import _close_open_titles

    pages, openings = _openings(
        ["Erster Abschnitt."], ["Zweiter Abschnitt."],
        ["Die drei Diplome samt", "ihrer Erneuerung durch", "den Kaiser und", "seinen",
         "Sohn."])
    _close_open_titles(openings, pages)
    assert openings[2] == {0: [0]}


def test_a_title_written_over_three_lines_is_one_heading(monkeypatch):
    import scriptor.reflow.running_elements as running

    real = running.opening_pages

    def widened(*args, **kwargs):
        found = real(*args, **kwargs)
        # as _close_open_titles leaves it
        found[1][0] = running._RunOnSpan(found[1][0] + [1, 2])
        return found

    monkeypatch.setattr(running, "opening_pages", widened)
    pages = _run(["Die Kloester des Westens samt", "ihrer Erneuerung", "durch den Kaiser."])
    cleaned, kept = _strip(pages)
    title = "Die Kloester des Westens samt ihrer Erneuerung durch den Kaiser."
    # Written with its depth: joined, a title may outrun the length one
    # printed line is held to.
    from scriptor.reflow.headings import mark_placed
    assert cleaned[1].split("\n")[0] == mark_placed(title, 1)
    assert kept == [(1, title)]
    assert "ihrer Erneuerung" not in "\n".join(cleaned[1].split("\n")[1:])


def test_a_run_that_begins_in_mid_sentence_opens_nothing():
    # The volume prints no running head on the chapter's first page; the run
    # begins on the second, and the text before it has not ended.
    pages = _run([_HEAD], before="und der Satz geht auf der naechsten Seite")
    cleaned, kept = _strip(pages)
    assert kept == []
    assert _HEAD not in cleaned[1]


def test_a_head_region_with_a_folio_is_a_running_page():
    cleaned, kept = _strip(_run(["17", _HEAD]))
    assert kept == []
    assert _HEAD not in cleaned[1]


def test_the_heading_lower_on_the_page_leaves_the_head_line_furniture():
    # Bauer p. 23: the running head is set from the state at the page's end,
    # and the heading it repeats stands further down the same page.
    cleaned, kept = _strip(_run([_HEAD, _DISTINCT[8], _DISTINCT[9], _HEAD]))
    assert kept == []
    assert cleaned[1].split("\n")[0] == _DISTINCT[8]


def test_a_wording_without_a_run_after_it_opens_nothing():
    # Nor is it furniture: two occurrences four pages apart never run, so the
    # line stays, unmarked (test_a_head_that_never_runs_is_left_standing).
    pages = _run([_HEAD], n=1) + [_DISTINCT[9]] * 3 + [f"30\n{_HEAD}\n{_DISTINCT[10]}"]
    cleaned, kept = _strip(pages)
    assert kept == []
    assert cleaned[1].split("\n")[0] == _HEAD


def test_a_mangled_folio_on_the_head_line_is_still_a_folio():
    # L'Empire chrétien p. 199: the OCR read the folio as "I99".
    cleaned, kept = _strip(_run([f"I99 {_HEAD}"]))
    assert kept == []


def test_a_section_opening_in_mid_page_has_its_heading_on_the_page_before():
    # Gli Actus p. XIX: the heading stands in the text of the page before, and
    # the running head begins on the next page, which opens nothing.
    pages = _run([_HEAD])
    pages[0] = pages[0].replace(_DISTINCT[7], _HEAD)
    cleaned, kept = _strip(pages)
    assert kept == []
    assert _HEAD not in cleaned[1]


def test_a_head_that_opens_again_and_again_is_the_volumes():
    # La masonería: the book title heads the pages of every chapter but its
    # first, so each chapter's second page looks like an opening.
    gap = [_DISTINCT[9], _DISTINCT[10], _DISTINCT[11]]
    pages = _run([_HEAD]) + gap + _run([_HEAD]) + gap + _run([_HEAD])
    assert len(_strip(_run([_HEAD]) + gap + _run([_HEAD]))[1]) == 2
    cleaned, kept = _strip(pages)
    assert kept == []
    assert all(_HEAD not in page for page in cleaned)


def test_a_roman_folio_changes_within_the_run():
    # Gli Actus: "LE DIREZIONI DELLA RICERCA XIX", two pages on "… XXI".
    pages = _run([f"{_HEAD} XVII"], n=1)
    pages += [f"{_HEAD} XIX\n{_DISTINCT[5]}", f"{_HEAD} XXI\n{_DISTINCT[6]}",
              f"{_HEAD} XXIII\n{_DISTINCT[7]}"]
    cleaned, kept = _strip(pages)
    assert kept == []


def test_a_roman_numeral_that_stays_is_the_sections_own():
    # Baynes: "XIV THE BYZANTINE INHERITANCE IN RUSSIA" over the whole chapter.
    head = f"XIV {_HEAD}"
    pages = _run([head], n=1) + [f"{n}\n{head}\n{_DISTINCT[4 + n % 3]}" for n in (20, 21, 22)]
    cleaned, kept = _strip(pages)
    assert kept == [(1, head)]


def test_each_chapter_number_is_a_head_of_its_own():
    # Chaldaean Oracles: "CHAPTER IV" two pages before "CHAPTER V", one
    # wording to the detector; neither the folio rule nor the cap may take
    # the fifth chapter's opening for the fourth's running page.
    pages = []
    for n, numeral in enumerate(("III", "IV", "V")):
        head = f"CHAPTER {numeral}"
        pages += [f"{_DISTINCT[11]}\nDamit endet das Kapitel.",
                  f"{head}\n{_DISTINCT[n]}\n{_DISTINCT[n + 1]}",
                  f"{30 + n}\n{head}\n{_DISTINCT[n + 4]}"]
    kept: list = []
    remove_running_headers(pages, ["CHAPTER IV"], RescuedFolios(len(pages)), kept=kept)
    assert [line for _i, line in kept] == ["CHAPTER III", "CHAPTER IV", "CHAPTER V"]


def test_a_head_the_ocr_spells_three_ways_is_one_head():
    # La masonería: the detector made three groups of "… MITO DE HIRAM".
    variants = ["TII. Mas alla del mito de Hiram", "MI. Mas alla del mito de Hiram",
                "TI. Mas alla del mito de Hikam"]
    pages = _run([variants[0]], n=1)
    pages += [f"{v}\n{_DISTINCT[4 + k]}" for k, v in enumerate(variants[1:])]
    kept: list = []
    remove_running_headers(pages, variants, RescuedFolios(len(pages)), kept=kept)
    assert kept == [(1, variants[0])]


def test_a_chapter_line_above_the_head_joins_the_title():
    # La masonería p. 87: "CAPÍTULO III" / "MÁS ALLÁ DEL MITO DE HIRAM"; the
    # numeral belongs to the chapter line, not to the running head.
    # The running head carries the numeral ("III. Más allá …"), so the two
    # opening lines together read as it, and neither alone does.
    head = f"III. {_HEAD}"
    pages = _run(["Kap. III", _HEAD], n=1)
    pages += [f"{n}\n{head}\n{_DISTINCT[n % 7]}" for n in (20, 21, 22)]
    kept: list = []
    remove_running_headers(pages, [head], RescuedFolios(len(pages)), kept=kept)
    assert kept == [(1, f"Kap. III {_HEAD}")]


def _excursus(opening, verso, recto, n=4):
    """A page before the section, its opening page (``opening`` over two lines
    of text), then pages headed alternately by ``verso`` and ``recto``."""
    pages = ["\n".join([*_DISTINCT[4:11], "Damit endet der Abschnitt."])]
    pages.append("\n".join([*opening, _DISTINCT[1], _DISTINCT[2]]))
    for i in range(n):
        pages.append(f"{20 + i}\n{(verso, recto)[i % 2]}\n{_DISTINCT[3 + i]}")
    return pages


def test_a_reference_above_a_title_the_head_spells_is_no_part_of_it():
    # Pückert p. 259: "Zweiter Excurs." / "(Zu S. 34.)" / "Die Unthaten des
    # Abts Fridugis zu Sithin." Joined to the title, the reference read as the
    # recto head, its "34.)" as a folio at the head's edge, and both titles
    # were stripped as furniture.
    verso, recto = "Zweiter Excurs.", "Die Unthaten des Abts Fridugis zu Sithin."
    pages = _excursus([verso, "(Zu S. 34.)", recto, "(Faelschungen.)"], verso, recto)
    kept: list = []
    cleaned = remove_running_headers(
        pages, [verso, recto], RescuedFolios(len(pages)), kept=kept)
    assert kept == [(1, verso), (1, recto)]
    assert cleaned[1].split("\n")[:4] == [MARK + verso, "(Zu S. 34.)", MARK + recto,
                                          "(Faelschungen.)"]


def test_a_numeral_above_a_title_the_head_spells_still_joins_it():
    # Kern, Gottesgnadentum (1914): "II." / "Die rechtliche Gebundenheit des
    # Herrschers.", the running head without the numeral.
    head = "Die rechtliche Gebundenheit des Herrschers."
    pages = _excursus(["II.", head], head, head)
    kept: list = []
    remove_running_headers(pages, [head], RescuedFolios(len(pages)), kept=kept)
    assert kept == [(1, f"II. {head}")]


def test_a_title_may_reach_below_the_head_region():
    # Pückert p. 248: "(Zu S. 15 Anm. 11.)" takes one of the head region's
    # three lines, and the title's second line is the fourth.
    from scriptor.reflow.headings import mark_placed

    verso, recto = "Erster Excurs.", "Die Kloester des Westens und Ostens"
    title = "Die Kloester des Westens und Ostens?"
    pages = _excursus([verso, "(Zu S. 15 Anm. 11.)", "Die Kloester des Westens",
                       "und Ostens?"], verso, recto)
    kept: list = []
    cleaned = remove_running_headers(
        pages, [verso, recto], RescuedFolios(len(pages)), kept=kept)
    assert kept == [(1, verso), (1, title)]
    assert cleaned[1].split("\n")[:3] == [MARK + verso, "(Zu S. 15 Anm. 11.)",
                                          mark_placed(title, 1)]
    assert "und Ostens?" not in "\n".join(cleaned[1].split("\n")[3:])


def test_a_head_that_never_runs_is_left_standing():
    # L'Empire chrétien: "CHAPITRE III" over a chapter's first page only.
    label = "CHAPITRE DEUX"
    gap = [_DISTINCT[9], _DISTINCT[10], _DISTINCT[11], _DISTINCT[8]]
    pages = []
    for k in range(3):
        pages += [f"{label}\n{_DISTINCT[k]}"] + gap
    rescued = RescuedFolios(len(pages))
    cleaned = remove_running_headers(pages, [label], rescued)
    assert sum(label in page for page in cleaned) == 3


def test_numbered_chapter_lines_stay_with_their_number():
    # Meisel: "1. Kapitel" … "15. Kapitel" over each chapter's first page,
    # about twenty pages apart; one up in twenty pages counts no pages.
    pages = []
    for n in range(1, 6):
        pages.append(f"{n}. Kapitel\n{_DISTINCT[n]}\n{_DISTINCT[n + 5]}")
        pages += [""] * 19
    cleaned, _headers, _ = strip_running_elements(pages)
    assert [n for n in range(1, 6) if f"{n}. Kapitel" in cleaned[(n - 1) * 20]] == [1, 2, 3, 4, 5]


def test_numbered_lines_that_count_the_pages_still_go():
    # The same wording far apart, but its number is the page's: a running
    # head the OCR lost on the pages between. The folio is rescued as before.
    pages = []
    for n in range(5):
        pages.append(f"Die Kloester des Westens {100 + 20 * n}\n{_DISTINCT[n]}\n{_DISTINCT[n + 5]}")
        pages += [""] * 19
    rescued = RescuedFolios(len(pages))
    cleaned, _headers, _ = strip_running_elements(pages, rescued)
    assert not any("Kloester" in page for page in cleaned)
    assert len(rescued.by_position()) == 5


def test_endnotes_at_the_head_of_their_pages_are_no_running_head():
    # Meisel's endnotes: "28 A. a. O., S. 292." opens a few of their pages
    # and stands on many more lower down.
    pages = []
    for k, n in enumerate((25, 3, 28, 12)):
        pages.append("\n".join([
            # The pages cited leap ahead of the volume's: they count nothing.
            f"{n} A. a. O., S. {290 + 17 * k}.", _DISTINCT[k], _DISTINCT[k + 4],
            f"{n + 1} A. a. O., S. {291 + 17 * k}.", f"{n + 2} A. a. O., S. {293 + 17 * k} f.",
            _DISTINCT[k + 8]]))
    cleaned, headers, _ = strip_running_elements(pages)
    assert headers == []
    assert all(page.startswith(f"{n} A. a. O.") for page, n in zip(cleaned, (25, 3, 28, 12)))


_WORDS = ("Einhard Alkuin Theodulf Paulinus Angilbert Hrabanus Walahfrid Notker "
          "Regino Thegan Nithard Hinkmar Lupus Sedulius Dhuoda Agobard Jonas Florus "
          "schrieb lobte tadelte kannte Reich Kloster Pfalz Kaiser Bischof Abt Synode "
          "Brief Vers Chronik Psalter Kapitular über gegen nach durch").split()
# Lines of prose, each its own (the head detection groups similar lines):
# eight words drawn without a pattern.
_PROSE = [" ".join(random.Random(seed).sample(_WORDS, 8)) + "." for seed in range(30)]


def test_a_head_that_runs_goes_though_sections_elsewhere_bear_its_name():
    # Militarizing Men: "Заключение" heads every other page of the
    # conclusion, and each chapter's last section is called so in mid-page.
    pages = []
    for n in range(5):
        pages.append("\n".join([_PROSE[n], _PROSE[n + 5], _PROSE[n + 10],
                                "Zusammenfassung", _PROSE[n + 15]]))
        pages += [""] * 9
    for n in range(5):
        pages.append(f"Zusammenfassung\n{_PROSE[20 + n]}\n{_PROSE[25 + n]}")
        pages.append("")
    cleaned, headers, _ = strip_running_elements(pages)
    assert headers == ["Zusammenfassung"]
    # The sections keep their name; the head goes after the page it opens.
    assert sum("Zusammenfassung" in page for page in cleaned[:50]) == 5
    assert not any("Zusammenfassung" in page for page in cleaned[52::2])


def test_a_head_a_spread_sets_in_mid_page_goes_with_its_folio():
    # Les apologistes grecs, scanned two pages to the image: the right page's
    # head "180  DE TATIEN À THÉOPHILE" stands in mid-image, numbered by the
    # pages it counts. It is the head, not the body printing its wording.
    pages = []
    for n in range(6):
        left = "\n".join([f"Die Apologeten der Kirche {101 + 4 * n}", _PROSE[n],
                          _PROSE[n + 6], _PROSE[n + 12]])
        right = f"{102 + 4 * n}  Die Apologeten der Kirche\n{_PROSE[n + 18]}"
        pages.append(left + "\n" + right if n % 2 else right + "\n" + left)
    cleaned, headers, _ = strip_running_elements(pages)
    assert headers
    assert not any(page.startswith(("Die Apologeten", "1")) for page in cleaned)


def test_a_running_head_that_also_opens_its_section_mid_page_still_goes():
    # Gli Actus p. XIX: the section's heading stands once in mid-page, its
    # running head on every page after.
    pages = [f"{_DISTINCT[0]}\n{_DISTINCT[1]}\n{_DISTINCT[2]}\n{_HEAD}\n{_DISTINCT[3]}"]
    pages += [f"{20 + i}\n{_HEAD}\n{_DISTINCT[4 + i]}" for i in range(4)]
    cleaned, headers, _ = strip_running_elements(pages)
    assert headers
    assert sum(_HEAD in page for page in cleaned) == 1


def test_a_number_closing_a_line_of_prose_is_no_folio():
    # Taubes p. 7: "Einleitung", then "… reichen von 1953".
    cleaned, kept = _strip(_run([_HEAD, "Die Texte reichen von 1953"]))
    assert kept == [(1, _HEAD)]


def test_a_title_whose_folio_stands_on_a_line_of_its_own_is_a_footer():
    # Fried, *Karl der Große*: the folio beside the last line of text, the
    # chapter title below it, each on its own line. Fewer pages than the
    # frequency path asks for; the bare numbers count them exactly.
    feet = {i: f"Der Knabe\n{30 + i}" for i in range(4, 18, 2)}
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert any(_strings_are_similar(f, "Der Knabe") for f in footers)


def test_a_title_beside_numbers_that_count_no_pages_is_no_footer():
    feet = {i: f"Der Knabe\n{30 + 3 * i}" for i in range(4, 18, 2)}
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert not any(_strings_are_similar(f, "Der Knabe") for f in footers)


def test_a_line_of_the_apparatus_beside_a_folio_is_no_footer():
    # "A. a. O., S. 292." repeats with the pages; it is no title.
    feet = {i: f"A. a. O., S. 29{i % 10}.\n{30 + i}" for i in range(4, 17)}
    footers = detect_running_footers(_wolf_pages(feet), min_occurrences=61)
    assert not any(_strings_are_similar(f, "A. a. O., S. 292.") for f in footers)
