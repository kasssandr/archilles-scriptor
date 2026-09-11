"""Heading metric: does the output carry the division the volume prints?

Kept apart, not averaged, because the failures do not cost the same
(Gliederungsmodell §3.6): a false heading is visible, a heading glued to its
paragraph loses structure silently, and a deleted title loses text silently.
The last one is therefore a list, like false apparatus in the region metric.
"""
from scriptor.eval.adapters import parse_prepared
from scriptor.eval.ground_truth import loads_truth
from scriptor.eval.headings import evaluate_headings


def _truth(*headings: tuple[str, int, str, str], chapter_level: int = 1):
    """(page, depth, designator, title) in document order."""
    lines = ['volume = "d"', 'pages = ["1"]', f"chapter_level = {chapter_level}"]
    for page, depth, designator, title in headings:
        lines += ["[[headings]]", f'page = "{page}"', f"depth = {depth}",
                  f'designator = "{designator}"', f'title = "{title}"']
    return loads_truth("\n".join(lines) + "\n")


def _measure(truth, text: str):
    return evaluate_headings(truth, parse_prepared(text))


BAUER = _truth(
    ("22", 2, "A.", "Problemstellung"),
    ("23", 2, "B.", "Gang der Darstellung"),
    ("24", 1, "Erstes Kapitel:", "Die bildliche Aneignung"),
    ("24", 2, "A.", "Bildliche Aneignung – eine Definition"),
    ("24", 3, "I.", "Aneignung als Rechtsbegriff"),
)


def test_a_heading_on_its_page_is_placed():
    r = _measure(_truth(("2", 1, "", "Einleitung")),
                 "[p. 1] Vorwort.\n\n[p. 2] Text.\n\n# Einleitung\n\nText.\n")
    assert r.placed_count == 1 and r.recall == 1.0 and r.precision == 1.0


def test_a_heading_that_opens_a_page_stands_before_its_marker():
    """Spec §4.2 (0.4.0): the marker of the block after a heading addresses
    the heading too. Read naively, every chapter would sit on the page before."""
    r = _measure(_truth(("24", 1, "Erstes Kapitel:", "Die bildliche Aneignung")),
                 "[p. 23] Text.\n\n# Erstes Kapitel: Die bildliche Aneignung\n\n"
                 "[p. 24]{#p-24} Im Folgenden wird.\n")
    assert r.placed_count == 1
    assert r.placed[0].page == "24"


def test_a_heading_on_another_page_is_missed_and_false():
    r = _measure(_truth(("3", 1, "", "Einleitung")),
                 "[p. 2] Text.\n\n# Einleitung\n\nText.\n\n[p. 3] More text.\n")
    assert r.placed_count == 0
    assert [h.title for h in r.missed] == ["Einleitung"]
    assert [(f.page, f.text) for f in r.false_headings] == [("2", "Einleitung")]


def test_the_designator_may_be_printed_or_lost():
    """Spec 0.4.0 keeps it; today's contents renderer drops roman numerals.
    Either way the heading stands -- the title carries the match."""
    truth = _truth(("5", 3, "I.", "Aneignung als Rechtsbegriff"),
                   ("5", 4, "1.", "Aneignung als allgemeinsprachlicher Begriff"),
                   chapter_level=3)
    r = _measure(truth, "[p. 5] Text.\n\n# Aneignung als Rechtsbegriff\n\nText.\n\n"
                        "# 1. Aneignung als allgemeinsprachlicher Begriff\n\nText.\n")
    assert r.placed_count == 2


def test_similar_titles_on_one_page_are_not_confused():
    truth = _truth(("28", 4, "1.", "Aneignung als allgemeinsprachlicher Begriff"),
                   ("28", 4, "2.", "Aneignung als philosophischer Begriff"),
                   chapter_level=4)
    r = _measure(truth, "[p. 28] Text.\n\n# 2. Aneignung als philosophischer Begriff\n\nText.\n")
    assert [m.truth.designator for m in r.placed] == ["2."]
    assert [h.designator for h in r.missed] == ["1."]


def test_a_repeated_title_is_matched_once_per_page():
    truth = _truth(("10", 2, "", "Fazit"), ("20", 2, "", "Fazit"), chapter_level=2)
    r = _measure(truth, "[p. 10] a\n\n## Fazit\n\nb\n\n[p. 20] c\n\n## Fazit\n\nd\n")
    assert [m.page for m in r.placed] == ["10", "20"]


def test_depth_counts_exact_and_steps_count_order():
    """A systematic offset keeps the shape of the tree; flattening does not."""
    truth = _truth(("1", 1, "", "Kapitel"), ("1", 2, "A.", "Abschnitt"),
                   ("1", 3, "I.", "Unterabschnitt"))
    flat = _measure(truth, "[p. 1] x\n\n# Kapitel\n\ny\n\n# A. Abschnitt\n\nz\n\n"
                           "# I. Unterabschnitt\n\nw\n")
    assert (flat.depth_exact, flat.steps_total, flat.steps_kept) == (1, 2, 0)
    offset = _measure(truth, "[p. 1] x\n\n## Kapitel\n\ny\n\n### A. Abschnitt\n\nz\n\n"
                             "#### I. Unterabschnitt\n\nw\n")
    assert (offset.depth_exact, offset.steps_total, offset.steps_kept) == (0, 2, 2)


def test_the_depth_of_the_chapters_is_read_off_the_placed_chapters():
    truth = _truth(("1", 1, "Erster Teil:", "Grundlagen"),
                   ("1", 2, "Erstes Kapitel:", "Begriffe"),
                   ("2", 2, "Zweites Kapitel:", "Geschichte"), chapter_level=2)
    r = _measure(truth, "[p. 1] x\n\n# Erster Teil: Grundlagen\n\n# Erstes Kapitel: Begriffe\n\n"
                        "y\n\n[p. 2] z\n\n# Zweites Kapitel: Geschichte\n\nw\n")
    assert (r.chapter_level, r.chapter_depth_found) == (2, 1)


def test_a_heading_glued_to_its_paragraph_is_missed_but_not_deleted():
    """Bauer §2.2: the text is there, the structure is gone, nothing reports it."""
    r = _measure(BAUER, "[p. 24] Text.\n\nA. Bildliche Aneignung – eine Definition "
                        "I. Aneignung als Rechtsbegriff Der Begriff der Aneignung findet sich.\n")
    assert {h.designator for h in r.missed} >= {"A.", "I."}
    assert "Aneignung als Rechtsbegriff" not in [h.title for h in r.deleted]
    assert r.running_in_text == []


def test_a_title_missing_from_its_page_is_deleted():
    """Bauer §2.7: a title removed as a running head on the page that prints it.
    That it survives in the contents list does not save it."""
    r = _measure(_truth(("24", 1, "", "Einleitung")),
                 "[region: contents]\n\n## Contents\n\n- [Einleitung](#p-24) — p. 24\n\n"
                 "[region: main]\n\n[p. 24] Text ohne die Überschrift.\n\n[p. 25] Mehr.\n")
    assert [h.title for h in r.deleted] == ["Einleitung"]


def test_a_running_head_glued_into_the_text_at_the_page_seam_is_found():
    """Bauer §2.1, p. 23: the running head names the section that begins on the
    page and lands in the reading flow at the seam, inside a hyphenated word."""
    r = _measure(BAUER, "[p. 22] In dieser Arbeit sollen künstlerische und "
                        "kommunikaB. [p. 23] Gang der Darstellung tive Aneignungen "
                        "gegenübergestellt werden.\n\nB. Gang der Darstellung Im ersten "
                        "Kapitel soll der Begriff eingeführt werden.\n")
    assert [(h.title, page) for h, page in r.running_in_text] == [
        ("Gang der Darstellung", "23")]
    assert "Gang der Darstellung" not in [h.title for h in r.deleted]


def test_a_running_head_beside_a_placed_heading_is_found_too():
    """Once a `#` line carries the heading, every seam occurrence is furniture."""
    r = _measure(BAUER, "[p. 22] Text kommunikaB. [p. 23] Gang der Darstellung tive "
                        "Aneignungen.\n\n## B. Gang der Darstellung\n\nIm ersten Kapitel.\n")
    assert [m.truth.title for m in r.placed] == ["Gang der Darstellung"]
    assert [(h.title, page) for h, page in r.running_in_text] == [
        ("Gang der Darstellung", "23")]


def test_a_heading_glued_to_the_paragraph_before_its_page_is_not_a_running_head():
    """Bauer p. 149: the section ends at the foot of p. 148, its paragraph was
    not closed, and the next heading ran into it -- after a finished sentence.
    The title repeating in the prose after it changes nothing."""
    truth = _truth(("149", 5, "a)", "Verletzung durch Frame-Links"),
                   ("51", 5, "a)", "Elaine Sturtevant"), chapter_level=5)
    r = _measure(truth, "[p. 148] durch einfache Hyperlinks. [^544] [p. 149]{#p-149} "
                        "a) Verletzung durch Frame-Links Nach nationalem Recht.\n\n"
                        "[p. 50] einordnen zu können.\n\n[p. 51]{#p-51} a) Elaine Sturtevant "
                        "Elaine Sturtevant war eine Künstlerin.\n")
    assert r.running_in_text == []
    assert r.deleted == []


def test_prose_naming_a_title_at_a_seam_is_not_a_running_head():
    """Bauer p. 47: 'die [p. 47] bildliche Aneignungen' is a sentence, not the
    running head 'Erstes Kapitel: Die bildliche Aneignung' -- which prints its
    designator."""
    r = _measure(BAUER, "[p. 46] ausgehend von der Kunstform, die [p. 47] bildliche "
                        "Aneignungen überhaupt erst zur Kunst erklärt hat.\n")
    assert r.running_in_text == []


def test_a_running_head_that_opens_a_paragraph_on_another_page_is_found():
    """Where the page broke between paragraphs, only the page tells: no
    heading of that wording stands there."""
    r = _measure(BAUER, "[p. 23] x\n\nB. Gang der Darstellung Im ersten Kapitel.\n\n"
                        "[p. 24] B. Gang der Darstellung Im zweiten Kapitel.\n")
    assert [(h.title, page) for h, page in r.running_in_text] == [
        ("Gang der Darstellung", "24")]


def test_a_title_two_headings_share_is_not_furniture_on_either_page():
    truth = _truth(("228", 3, "I.", "Definition"), ("254", 3, "I.", "Definition"),
                   chapter_level=3)
    r = _measure(truth, "[p. 228] x.\n\n## I. Definition\n\nText.\n\n"
                        "[p. 254]{#p-254} I. Definition Der kommunikative Ansatz.\n")
    assert r.running_in_text == []


def test_a_letter_heading_of_an_index_is_not_sought_at_the_seams():
    """An outline lists the index letters A, B, C; one letter stands next to
    every page marker somewhere. Too short to tell a running head from prose."""
    truth = _truth(("300", 2, "", "A"), chapter_level=2)
    r = _measure(truth, "[p. 300] x\n\n## A\n\nAbel.\n\n[p. 301] and so the "
                        "argument [p. 302] a claim runs on.\n")
    assert r.running_in_text == []


def test_a_heading_cut_at_the_end_of_its_line_is_placed_but_truncated():
    """Bauer §2.4: the rest of the title opens the paragraph below."""
    truth = _truth(("40", 4, "3.",
                    "Rennaissance-Humanismus und die Individualität der Künstlerpersönlichkeit"),
                   chapter_level=4)
    r = _measure(truth, "[p. 40] x\n\n# 3. Rennaissance-Humanismus und die Individualität der\n\n"
                        "Künstlerpersönlichkeit Durch das Aufkommen.\n")
    assert r.placed_count == 1 and r.placed[0].truncated
    assert r.deleted == []


def test_a_heading_line_that_runs_on_past_the_title_is_placed():
    """The reference may be shorter than the line: outlines cut long titles
    ('... überhau'), and a heading may carry words of its paragraph."""
    truth = _truth(("6", 2, "", "Ueber den Begriff der Wissenschafts"),
                   chapter_level=2)
    r = _measure(truth, "[p. 6] x\n\n## Ueber den Begriff der Wissenschaftslehre "
                        "überhaupt und seine Grenzen\n\nText.\n")
    assert r.placed_count == 1 and not r.placed[0].truncated


def test_a_numbered_line_the_contents_do_not_know_is_a_false_heading():
    """Bauer §2.5: theses 2 to 12 came out as headings."""
    r = _measure(_truth(("200", 1, "", "Zusammenfassende Thesen")),
                 "[p. 200] x\n\n# Zusammenfassende Thesen\n\n"
                 "# 2. Die Aneignung von Bildern hat sich im Digitalen zu einem Massenphänomen\n\n"
                 "entwickelt.\n")
    assert r.placed_count == 1
    assert [f.text[:2] for f in r.false_headings] == ["2."]
    assert r.precision == 0.5


def test_a_volume_without_heading_truth_measures_nothing():
    r = evaluate_headings(loads_truth('volume = "d"\npages = ["1"]\n'),
                          parse_prepared("[p. 1] x\n\n# Kapitel\n\ny\n"))
    assert r.total == 0 and r.false_headings == []
