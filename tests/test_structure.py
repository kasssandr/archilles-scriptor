"""The division of a volume, one model for every path (Gliederungsmodell B2).

A tree of printed headings, a numbering scheme table learnt per volume from
its own contents, a chapter level that is declared rather than guessed from
'#', and one derivation of `chapter` / `section_title` / `section` for PDF,
EPUB and the master alike. Pure functions; nothing here reads a page.
"""
import json
import tomllib
from pathlib import Path

import pytest

from scriptor import structure as st
from scriptor.languages import NOT_ATTESTED, SUPPORTED_LANGUAGES

ROOT = Path(__file__).resolve().parents[1]
BAUER_TRUTH = ROOT / "eval" / "corpus" / "bauer-aneignung" / "truth.toml"


def _entries(*rows):
    """(text, page[, indent[, region]]) -> contents entries in reading order."""
    return [st.Entry(*row) for row in rows]


# ── schemes ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, scheme, designator", [
    ("Erstes Kapitel: Die bildliche Aneignung", "word-ordinal", "Erstes Kapitel:"),
    ("A. Bildliche Aneignung – eine Definition", "letter-upper", "A."),
    ("I. Aneignung als Rechtsbegriff", "roman-upper", "I."),
    ("1. Aneignung als allgemeinsprachlicher Begriff", "arabic", "1."),
    ("a) Elaine Sturtevant", "letter-lower-paren", "a)"),
    ("aa) Unbestimmte Zahl potenzieller Adressaten", "letter-double-paren", "aa)"),
    ("(1) Kunstbegriff des Art. 5 Abs. 3 GG", "paren-arabic", "(1)"),
    ("2.3 Lexical Search", "arabic-dotted-2", "2.3"),
    ("1 Introduction", "arabic-bare", "1"),
    ("IV Themistios und Valens", "roman-upper-bare", "IV"),
    ("§ 3 Der Begriff", "section-sign", "§ 3"),
    ("b. The second reading", "letter-lower-dot", "b."),
    ("• La humanidad de Carlos", "bullet", "•"),
    ("Zweiter Teil: Grundlagen", "word-part", "Zweiter Teil:"),
    ("PART II: The Argument", "word-part", "PART II:"),
    ("Capítulo IV. Los orígenes", "word-ordinal", "Capítulo IV."),
    ("Hoofdstuk 3 - De raadpensionaris", "word-ordinal", "Hoofdstuk 3 -"),
    ("Einleitung", "", ""),
])
def test_the_printed_designator_names_its_scheme(text, scheme, designator):
    assert st.scheme_of(text, roman_volume=True)[:2] == (scheme, designator)


def test_a_lone_c_is_a_letter_even_in_a_volume_with_roman_numerals():
    """Bauer: 'C. Eingriff in Verwertungsrechte' is the third section, not the
    hundredth part. Only I, V and X are read as lone roman numerals."""
    assert st.scheme_of("C. Eingriff in Verwertungsrechte", roman_volume=True)[0] == "letter-upper"
    assert st.scheme_of("V. Begriff des Bildlichen", roman_volume=True)[0] == "roman-upper"
    assert st.scheme_of("V. Begriff des Bildlichen", roman_volume=False)[0] == "letter-upper"


def test_a_word_form_of_an_unattested_language_is_not_guessed():
    """Italian prints 'Capitolo 3' -- no volume in the corpus attests it, so the
    line stays unnumbered, which is the safe direction."""
    assert st.scheme_of("Capitolo 3 Le fonti", roman_volume=True)[0] == ""


@pytest.mark.parametrize("catalogue", ["CHAPTER_WORDS", "PART_WORDS"])
@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_language_answers_for_every_word_form(catalogue, language):
    entry = getattr(st, catalogue)
    assert language in entry, f"{catalogue}/{language}: kein Eintrag"
    assert entry[language] is NOT_ATTESTED or (
        isinstance(entry[language], tuple) and entry[language])


# ── the scheme table ─────────────────────────────────────────────────

def _bauer_entries():
    heads = tomllib.loads(BAUER_TRUTH.read_text(encoding="utf-8"))["headings"]
    body = [h for h in heads if h.get("region") not in ("preface", "contents")]
    entries = [st.Entry(f"{h.get('designator', '')} {h['title']}".strip(), h["page"])
               for h in body]
    return body, entries


def test_bauer_learns_seven_depths_in_the_order_it_prints_them():
    _, entries = _bauer_entries()
    table = st.learn_schemes(entries).table
    assert [(r.scheme, r.depth) for r in table.rows] == [
        ("word-ordinal", 1), ("letter-upper", 2), ("roman-upper", 3),
        ("arabic", 4), ("letter-lower-paren", 5), ("letter-double-paren", 6),
        ("paren-arabic", 7),
    ]


def test_bauer_every_numbered_entry_gets_its_printed_depth():
    """The pure stack of Befund §5.3 gets 7 of Bauer's numbered entries right:
    'Einleitung' with its 'A.' and 'B.' stands before the first chapter and
    pushes 'Erstes Kapitel' down. G6 measured the amendments."""
    heads, entries = _bauer_entries()
    depths = st.learn_schemes(entries).depths
    wrong = [(h["title"], d, h["depth"]) for h, d in zip(heads, depths)
             if h.get("designator") and d != h["depth"]]
    assert wrong == []


def test_a_numbered_entry_on_the_page_of_an_unnumbered_one_is_its_child():
    """Bauer: 'Einleitung' 19 › 'A. Problemaufriss' 19."""
    learnt = st.learn_schemes(_entries(("Einleitung", "19"), ("A. Problemaufriss", "19"),
                                       ("B. Gang der Darstellung", "23"),
                                       ("Erstes Kapitel: Aneignung", "24"),
                                       ("A. Definition", "24")))
    assert learnt.depths == [1, 2, 2, 1, 2]


def test_a_numbered_entry_pages_after_an_unnumbered_one_is_its_sibling():
    learnt = st.learn_schemes(_entries(("Introduction", "1"), ("I. The Oracles", "9"),
                                       ("II. The Theurgists", "40"), ("Conclusion", "90")))
    assert learnt.depths == [1, 1, 1, 1]


def test_parts_stand_over_chapters_and_a_chapter_closes_down_to_its_part():
    learnt = st.learn_schemes(_entries(
        ("Erster Teil: Grundlagen", "1"), ("Erstes Kapitel: Begriffe", "3"),
        ("A. Der Begriff", "3"), ("Zweites Kapitel: Geschichte", "20"),
        ("Zweiter Teil: Anwendung", "40"), ("Drittes Kapitel: Fälle", "42")))
    assert learnt.depths == [1, 2, 3, 2, 1, 2]


def test_carlomagno_numbers_chapters_in_roman_and_sections_with_a_bullet():
    learnt = st.learn_schemes(_entries(
        ("I. El joven Carlos", "11"), ("• La humanidad de Carlos", "12"),
        ("• El heredero", "20"), ("II. El rey", "31"), ("• Las campañas", "33")))
    assert [(r.scheme, r.depth) for r in learnt.table.rows] == [("roman-upper", 1), ("bullet", 2)]
    assert learnt.depths == [1, 2, 2, 1, 2]


def test_a_dotted_number_carries_its_own_depth():
    learnt = st.learn_schemes(_entries(("1 Introduction", "1"), ("1.1 Scope", "2"),
                                       ("1.1.1 Detail", "3"), ("1.2 Method", "5"),
                                       ("2 Results", "9")))
    assert learnt.depths == [1, 2, 3, 2, 1]


def test_unnumbered_entries_under_a_word_form_are_its_sections():
    """De eerste minister sets chapters and sections flush left, the sections
    unnumbered. Against the outlines this rule keeps 128 of 146 changes of
    level; the Befund's 'depth of the entry before' kept 112 (G6)."""
    learnt = st.learn_schemes(_entries(
        ("Hoofdstuk 1 - Oldenbarnevelt", "11"), ("Raad en pensionaris", "12"),
        ("Werkwijze", "15"), ("Hoofdstuk 2 - De Witt", "30"), ("Bronnen", "31")))
    assert learnt.depths == [1, 2, 2, 1, 2]


def test_an_unnumbered_entry_after_a_numbered_section_is_its_sibling():
    learnt = st.learn_schemes(_entries(("1. Begriffe", "1"), ("2. Geschichte", "9"),
                                       ("Schluss", "40")))
    assert learnt.depths == [1, 1, 1]


def test_the_left_edge_says_top_where_the_volume_indents_at_all():
    learnt = st.learn_schemes(_entries(
        ("Erstes Kapitel: A", "1", 0.0), ("A. Eins", "1", 20.0), ("I. Zwei", "2", 36.0),
        ("II. Drei", "5", 36.0),
        ("Zusammenfassende Thesen", "317", 0.0)))
    assert learnt.depths == [1, 2, 3, 3, 1]


def test_a_region_title_is_top():
    learnt = st.learn_schemes(_entries(("1. Begriffe", "1"), ("a) Eins", "2"),
                                       ("Literaturverzeichnis", "325", None, "bibliography")))
    assert learnt.depths == [1, 2, 1]


def test_the_table_takes_the_depth_most_entries_of_a_scheme_stand_on():
    """A lost contents line makes one 'a)' jump a level; the table does not."""
    table = st.learn_schemes(_entries(
        ("I. Eins", "1"), ("1. Zwei", "2"), ("a) Drei", "3"), ("b) Vier", "4"),
        ("II. Fünf", "9"), ("a) Sechs", "10"), ("1. Sieben", "11"), ("a) Acht", "12"))).table
    assert table.depth_of("letter-lower-paren") == 3


# ── the tree ─────────────────────────────────────────────────────────

def _bauer_tree():
    return st.Tree.from_headings([
        (1, "Einleitung"),
        (2, "A. Problemaufriss"),
        (1, "Erstes Kapitel: Die bildliche Aneignung"),
        (2, "A. Bildliche Aneignung – eine Definition"),
        (3, "II. Aneignung als kultureller Begriff"),
        (4, "1. Aneignung als allgemeinsprachlicher Begriff"),
        (1, "Zusammenfassende Thesen"),
    ])


def test_from_headings_splits_designator_and_title():
    node = _bauer_tree().nodes[5]
    assert (node.depth, node.designator, node.scheme, node.title) == (
        4, "1.", "arabic", "Aneignung als allgemeinsprachlicher Begriff")


def test_from_headings_reads_an_emphasised_seventh_depth():
    """Briefing §8.3: a depth the print does not tell from the one above is
    written '###### *Titel*'; the emphasis is typography, not title."""
    tree = st.Tree.from_headings([(6, "aa) Kunstspezifisch"), (6, "*Kunstbegriff des GG*")])
    assert tree.nodes[1].title == "Kunstbegriff des GG"


def test_fields_below_the_chapter_level():
    tree = _bauer_tree()
    fields = tree.fields_of(5, chapter_level=1)
    assert fields.chapter == "Erstes Kapitel: Die bildliche Aneignung"
    assert fields.section_title == "1. Aneignung als allgemeinsprachlicher Begriff"
    assert fields.section == "A.II.1"


def test_fields_of_a_chapter_itself():
    fields = _bauer_tree().fields_of(2, chapter_level=1)
    assert (fields.chapter, fields.section_title, fields.section) == (
        "Erstes Kapitel: Die bildliche Aneignung", "", "")


def test_a_node_above_the_chapter_level_is_its_own_chapter():
    """An 'Einleitung' beside parts: chapters sit on depth 2, the introduction
    on 1, and it is still what its paragraphs belong to."""
    tree = st.Tree.from_headings([(1, "Einleitung"), (1, "Erster Teil: Grundlagen"),
                                  (2, "Erstes Kapitel: Begriffe")])
    assert tree.fields_of(0, chapter_level=2).chapter == "Einleitung"
    assert tree.fields_of(2, chapter_level=2).chapter == "Erstes Kapitel: Begriffe"


def test_a_jump_in_depth_finds_the_nearest_ancestor():
    tree = st.Tree.from_headings([(1, "Erstes Kapitel: A"), (3, "I. Tief")])
    assert tree.ancestors(1) == [0]
    assert tree.fields_of(1, chapter_level=1).chapter == "Erstes Kapitel: A"


# ── the chapter level (Befund §3.2) ──────────────────────────────────

def _level(rows, region_of=None):
    return st.Tree.from_headings(rows, region_of=region_of).chapter_level()


def test_chapter_level_bauer_is_one():
    regions = {"Literaturverzeichnis": "bibliography"}
    assert _level([(1, "Einleitung"), (2, "A. Problemaufriss"),
                   (1, "Erstes Kapitel: X"), (2, "A. Y"),
                   (1, "Zweites Kapitel: Z"), (1, "Zusammenfassende Thesen"),
                   (1, "Literaturverzeichnis")], regions.get) == 1


def test_chapter_level_asclepios_is_two():
    """Level 1 holds 'Inhoudsopgave' (a region) and one other entry; the
    region does not count towards the two a chapter level needs."""
    regions = {"Inhoudsopgave": "contents"}
    rows = [(1, "Inhoudsopgave"), (2, "Woord vooraf"), (2, "Inleiding")]
    rows += [(2, f"{n}. Hoofdstuk {n}") for n in range(1, 18)]
    rows += [(1, "Verantwoording van de afbeeldingen")]
    assert _level(rows, regions.get) == 2


def test_chapter_level_themistios_is_two():
    """Level 1 is the bare ISBN, twice: packaging, never a chapter."""
    assert _level([(1, "9783110224764"), (2, "I. Einleitung"), (2, "II. Die Reden"),
                   (1, "9783110224771"), (2, "III. Themistios")]) == 2


def test_chapter_level_under_parts_is_two():
    assert _level([(1, "Erster Teil: A"), (2, "Erstes Kapitel: B"), (2, "Zweites Kapitel: C"),
                   (1, "Zweiter Teil: D"), (2, "Drittes Kapitel: E")]) == 2


def test_a_level_that_numbers_itself_as_subsections_is_not_the_chapter_level():
    assert _level([(1, "1.1 Scope"), (1, "1.2 Aims"), (2, "a) Detail"),
                   (2, "b) More")]) == 2


# ── the master line ──────────────────────────────────────────────────

def test_depths_one_to_six_are_their_own_markdown_level():
    node = st.Node(depth=4, designator="1.", scheme="arabic", title="Platon")
    assert st.heading_markdown(node, st.SchemeTable([])) == "#### 1. Platon"


def test_a_seventh_depth_with_its_own_designator_is_six_hashes():
    table = st.SchemeTable([st.SchemeRow("letter-double-paren", 6, 12),
                            st.SchemeRow("paren-arabic", 7, 4)])
    node = st.Node(depth=7, designator="(1)", scheme="paren-arabic", title="Kunstbegriff")
    assert st.heading_markdown(node, table) == "###### (1) Kunstbegriff"


def test_a_seventh_depth_the_print_does_not_distinguish_is_emphasised():
    table = st.SchemeTable([st.SchemeRow("", 6, 3)])
    node = st.Node(depth=7, title="Kunstbegriff")
    assert st.heading_markdown(node, table) == "###### *Kunstbegriff*"


@pytest.mark.parametrize("text, title", [
    ("*Kunstbegriff*", "Kunstbegriff"), ("_Kunstbegriff_", "Kunstbegriff"),
    ("(1) *Kunstbegriff*", "(1) *Kunstbegriff*"), ("*a* and *b*", "*a* and *b*"),
    ("Kunstbegriff", "Kunstbegriff"),
])
def test_only_one_emphasis_around_the_whole_text_is_stripped(text, title):
    assert st.strip_heading_emphasis(text) == title


# ── regions and packaging ────────────────────────────────────────────

@pytest.mark.parametrize("types, region", [
    ("bibliography", "bibliography"), ("toc", "contents"), ("index", "index"),
    ("frontmatter", None), ("backmatter", None), ("footnote", None),
    ("chapter", None), ("preface", "preface"), ("copyright-page", "front-matter"),
    ("bodymatter chapter", None), ("backmatter bibliography", "bibliography"),
    ("unknown-type", None),
])
def test_epub_type_names_a_region_only_where_anhang_b1_says_so(types, region):
    assert st.region_for_epub_type(types) == region


def test_every_epub_region_is_a_spec_name():
    from scriptor.reflow.regions import REGION_NAMES
    assert {r for r in st.EPUB_TYPE_REGIONS.values() if r} <= set(REGION_NAMES)


@pytest.mark.parametrize("title", ["Cover", "Half Title", "Portada", "9783110224764",
                                   "Umschlag", "Copertina"])
def test_packaging_is_never_a_node(title):
    assert st.is_packaging(title)


def test_chapters_takes_its_packaging_words_from_structure():
    """One list, not two copies. (Identity alone would not show it: re caches
    compiled patterns, so two identical copies compare as one object.)"""
    import inspect

    from scriptor.reflow import chapters
    assert chapters._PACKAGING is st.PACKAGING_WORDS
    assert "re.compile" not in inspect.getsource(chapters).split("_PACKAGING =", 1)[1].split("\n", 1)[0]


# ── the sidecar ──────────────────────────────────────────────────────

def _structure():
    table = st.SchemeTable([st.SchemeRow("word-ordinal", 1, 5), st.SchemeRow("letter-upper", 2, 17)])
    headings = [
        st.Node(depth=1, designator="Erstes Kapitel:", scheme="word-ordinal",
                title="Die bildliche Aneignung", page="24", pos=24,
                sources=[st.Witness("contents", "title on the expected page")]),
        st.Node(depth=2, designator="A.", scheme="letter-upper", title="Definition",
                page="24", pos=24, sources=[st.Witness("typography-2027", "a source from the future")]),
        st.Node(depth=1, title="Literaturverzeichnis", page="325", pos=325,
                region="bibliography", sources=[st.Witness("contents")]),
    ]
    return st.Structure(chapter_level=1, schemes=table, headings=headings,
                        unplaced=[{"text": "B. Untersuchungsgegenstände", "page": "46"}],
                        rejected=[{"text": "2. Die Aneignung von Bildern", "page": "317",
                                   "reason": "not-in-contents"}])


def test_the_sidecar_round_trips(tmp_path):
    structure = _structure()
    master = tmp_path / "book.md"
    json_text, txt = st.render_structure_sidecar(structure, "book.md")
    (tmp_path / "book.md.structure.json").write_text(json_text, encoding="utf-8")
    back = st.read_structure_sidecar(master)
    assert back == structure
    assert json.loads(json_text)["version"] == st.SIDECAR_VERSION
    assert "  A. Definition" in txt and "B. Untersuchungsgegenstände" in txt


def test_an_unknown_source_is_carried_through(tmp_path):
    json_text, _ = st.render_structure_sidecar(_structure(), "book.md")
    (tmp_path / "book.md.structure.json").write_text(json_text, encoding="utf-8")
    back = st.read_structure_sidecar(tmp_path / "book.md")
    assert back.headings[1].sources[0].source == "typography-2027"


def test_a_missing_sidecar_is_none_and_an_unknown_version_is_refused(tmp_path):
    assert st.read_structure_sidecar(tmp_path / "book.md") is None
    (tmp_path / "book.md.structure.json").write_text('{"version": 99}', encoding="utf-8")
    with pytest.raises(ValueError):
        st.read_structure_sidecar(tmp_path / "book.md")


def test_the_sidecar_is_stable_json():
    assert st.render_structure_sidecar(_structure(), "b")[0] == \
        st.render_structure_sidecar(_structure(), "b")[0]


def test_the_block_line_says_depths_chapter_level_and_sources():
    assert st.describe(_structure()) == (
        "2 levels, chapters on level 1, 3 headings (2 contents, 1 typography-2027)")
