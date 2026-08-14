"""Page labels: detection, decoding, and the anchor collision they would cause
if a decoded ordinal were ever used as a page identity.

Contract under test: archilles/docs/WATCHDOG_AND_WIKI.md §II.5 — the citable
page is the *printed* label, which may be roman.
"""
import pytest

from scriptor.reflow.core import main as reflow_main
from scriptor.reflow.pagelabel import decode_label, detect_page_label
from scriptor.reflow.toc import inject_page_anchors


# --- detection ----------------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("312", "312"),
    ("  23 ", "23"),
    ("xiv", "xiv"),               # roman frontmatter label
    ("vi", "vi"),
    ("146 WILHELM HEIL", "146"),  # label paired with a running head
    ("xiv PREFACE", "xiv"),
])
def test_detect_returns_label_verbatim(line, expected):
    assert detect_page_label(line) == expected


@pytest.mark.parametrize("line", [
    "1990 war ein gutes Jahr fuer die Forschung",  # leading year in prose
    "3. Die Probleme um Welf VI. im Vergleich",
    "12345", "0", "",
    "i", "v", "x", "l",     # single letters: rejected on purpose (see pagelabel)
    "BOOK II",              # uppercase roman is a division number, not a page
    "CHAPTER XIV",
    "XIV",
    "ill", "did", "dim", "mill",  # words that flirt with roman syntax
])
def test_detect_rejects_non_labels(line):
    assert detect_page_label(line) is None


def test_single_letter_rejection_protects_the_body():
    """A lone 'l' is an OCR misreading of '1' far more often than roman 50 —
    and a line taken for a page label is deleted from the body. Under-detect."""
    assert detect_page_label("l") is None
    assert decode_label("l") is None


# --- decoding is for ordering, never for identity -----------------------------

@pytest.mark.parametrize("label,value", [
    ("xiv", 14), ("14", 14), ("ii", 2), ("xl", 40), ("mcmxcix", 1999), ("312", 312),
])
def test_decode_label(label, value):
    assert decode_label(label) == value


def test_roman_and_arabic_can_share_an_ordinal():
    """The reason anchors key on the label. If they keyed on this value, a TOC
    link to page 14 would land in the roman-paginated preface."""
    assert decode_label("xiv") == decode_label("14")


# --- the collision, at the layer where it would bite --------------------------

def test_anchor_targets_arabic_page_not_the_roman_namesake():
    doc = "Vorwort [p. xiv] Ende\n\nHaupttext [p. 14] weiter"
    out = inject_page_anchors(doc, {"14"})
    assert "[p. 14]{#p-14}" in out
    assert "[p. xiv]{#p-14}" not in out
    assert "[p. xiv]" in out          # preface marker survives, unanchored


def test_anchor_targets_roman_page_when_asked():
    doc = "Vorwort [p. xiv] Ende\n\nHaupttext [p. 14] weiter"
    out = inject_page_anchors(doc, {"xiv"})
    assert "[p. xiv]{#p-xiv}" in out
    assert "[p. 14]{#p-14}" not in out


# --- end to end ---------------------------------------------------------------

def _write_pages(tmp_path, *page_texts):
    pages = tmp_path / "pages"
    pages.mkdir()
    for i, text in enumerate(page_texts, start=1):
        (pages / f"{i:08d}.txt").write_text(text, encoding="utf-8")
    return pages


def test_reflow_emits_roman_marker_and_drops_the_label_line(tmp_path):
    # Two pages per run: a single reading no longer establishes a numbering
    # system on its own (FitParams.min_attested).
    src = _write_pages(
        tmp_path,
        "Das Vorwort erklaert die Absicht des Verfassers ausfuehrlich.\nxiv\n",
        "Das Vorwort setzt seinen Gedankengang auf dieser Seite fort.\nxv\n",
        "Der Haupttext beginnt und nennt eine Quelle im Satz weiter.\n312\n",
        "Der Haupttext fuehrt den Gedanken auf der Folgeseite weiter.\n313\n",
    )
    out = tmp_path / "book.md"
    reflow_main(str(src), str(out), "md")
    text = out.read_text(encoding="utf-8")

    assert "[p. xiv]" in text          # the preface is citable
    assert "[p. 312]" in text
    # The label line must not survive as body text — that was the old failure.
    assert not any(ln.strip() == "xiv" for ln in text.splitlines())


def test_physical_index_is_recorded_for_every_page(tmp_path):
    """Counterpart to page_number in the archilles chunk schema. Stored, not yet
    emitted — the marker syntax for it is a cross-repo decision."""
    from scriptor.reflow.core import parse_page
    pages = [parse_page("Kein gedrucktes Label auf dieser Seite.\n"),
             parse_page("Zweite Seite ohne Label.\n")]
    for ordinal, pg in enumerate(pages, start=1):
        pg.index = ordinal
    assert [pg.index for pg in pages] == [1, 2]
    assert all(pg.label is None for pg in pages)   # nothing printed, nothing invented


def test_style_of_tells_the_numbering_systems_apart():
    from scriptor.reflow.pagelabel import style_of

    assert style_of("312") == "arabic"
    assert style_of("xiv") == "roman-lower"
    assert style_of("XIV") == "roman-upper"


def test_style_of_returns_none_for_what_is_not_a_label():
    from scriptor.reflow.pagelabel import style_of

    assert style_of("Kapitel") is None
    assert style_of("") is None


def test_style_of_accepts_uppercase_roman_although_the_detector_does_not():
    # detect_page_label refuses uppercase roman on purpose ("BOOK II" in a
    # running head must not be read as a page label). The catalogue states its
    # labels directly and does print "XIV", so the classifier has to know the
    # style even where the detector would never produce it.
    from scriptor.reflow.pagelabel import detect_page_label, style_of

    assert detect_page_label("XIV") is None
    assert style_of("XIV") == "roman-upper"
