"""The reader of the prepared format, where a consumer may import it from.

parse_prepared moved here out of eval/ (the benchmark's workshop); load_bundle adds
what travels beside the master -- the metadata block and the pagination sidecar
(spec §4.1, §6.3). Archilles reads a bundle through this module instead of keeping
a second copy of the grammar.
"""
import json

import pytest

from scriptor.document import Bundle, load_bundle, parse_prepared
from scriptor.reflow.regions import FORMAT_VERSION, render_metadata_block

BODY = """[p. xiv] Ein Vorwort, römisch gezählt.

[region: bibliography]

[p. 1] Ein Satz mit Anker [^1].

[^1]: Die Note.
"""


def _sidecar(pages, version=1):
    return json.dumps({"version": version,
                       "profile": {"edge": "bottom", "attested": 0.5, "band": None},
                       "segments": [], "pages": pages, "rejected": []})


def _bundle(tmp_path, *, block=True, sidecar=None, body=BODY):
    master = tmp_path / "book.md"
    head = render_metadata_block("scientific", "bottom edge, 50% of pages attested")
    master.write_text((head + "\n\n" if block else "") + body, encoding="utf-8")
    if sidecar is not None:
        (tmp_path / "book.md.pagination.json").write_text(sidecar, encoding="utf-8")
    return master


PAGES = [
    {"pos": 3, "label": "xiv", "source": "printed", "confidence": 1.0},
    {"pos": 5, "label": "1", "source": "computed", "confidence": 0.5},
]


# the move -------------------------------------------------------------------

def test_the_eval_adapter_uses_this_reader_not_a_copy():
    from scriptor.eval import adapters
    assert adapters.parse_prepared is parse_prepared


def test_parse_prepared_reads_what_it_read_before():
    doc = parse_prepared(render_metadata_block() + "\n\n" + BODY)
    assert [lbl for lbl, _ in doc.page_marks] == ["xiv", "1"]
    assert [name for name, _ in doc.region_marks] == ["bibliography"]
    assert doc.footnotes[0].definition == "Die Note."


# the bundle -----------------------------------------------------------------

def test_a_bundle_carries_its_declaration(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert isinstance(b, Bundle)
    assert b.format_version == FORMAT_VERSION
    assert b.chunking_strategy == "scientific"
    assert b.pagination == "bottom edge, 50% of pages attested"
    assert b.text.endswith(BODY)


def test_physical_page_and_source_come_from_the_sidecar(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert b.physical_page_of("xiv") == 3          # roman label, verbatim
    assert b.source_of("xiv") == "printed"
    assert b.physical_page_of("1") == 5
    assert b.source_of("1") == "computed"


def test_a_label_the_sidecar_does_not_know_has_no_page(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES)))
    assert b.physical_page_of("73, ed. Buber") is None
    assert b.source_of("73, ed. Buber") is None


def test_without_a_sidecar_the_bundle_still_reads(tmp_path):
    """A missing sidecar is no error: the text is whole (spec §3), only the
    physical page is unknown -- and unknown is None, never a guess."""
    b = load_bundle(_bundle(tmp_path))
    assert b is not None
    assert b.pages == []
    assert b.physical_page_of("xiv") is None
    assert b.source_of("xiv") is None


def test_a_sidecar_that_found_no_printed_number_is_a_normal_bundle(tmp_path):
    # Seven of thirty library volumes in M1 (EPUB conversions, scans of spreads):
    # the sidecar exists and its page list is empty.
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar([]), body="Text ohne Seitenzahl.\n"))
    assert b is not None and b.pages == []
    assert b.resolve_marks(parse_prepared(b.text)) == []


def test_a_master_without_a_block_is_not_a_bundle(tmp_path):
    assert load_bundle(_bundle(tmp_path, block=False, sidecar=_sidecar(PAGES))) is None


def test_a_block_without_format_version_is_not_a_bundle(tmp_path):
    master = tmp_path / "book.md"
    master.write_text("---\nchunking_strategy: basic\n---\n\n" + BODY, encoding="utf-8")
    assert load_bundle(master) is None


def test_chunking_strategy_defaults_to_basic(tmp_path):
    # Spec §4.1: every field is optional, and the absent strategy is basic.
    master = tmp_path / "book.md"
    master.write_text(f"---\nformat_version: {FORMAT_VERSION}\n---\n\n" + BODY, encoding="utf-8")
    assert load_bundle(master).chunking_strategy == "basic"


def test_a_sidecar_of_an_unknown_version_is_refused(tmp_path):
    with pytest.raises(ValueError, match="version"):
        load_bundle(_bundle(tmp_path, sidecar=_sidecar(PAGES, version=2)))


def test_an_unknown_source_is_passed_through(tmp_path):
    """Spec §6.3: the list has grown twice. The consumer treats a value it does
    not know as asserted -- so it must see the value, not a replacement."""
    pages = [{"pos": 3, "label": "xiv", "source": "ocr-verified", "confidence": 0.9}]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages)))
    assert b.source_of("xiv") == "ocr-verified"


# labels that repeat ---------------------------------------------------------

REPEATING = """[p. 1] Erster Teil, erste Seite.

[p. 2] Erster Teil, zweite Seite.

[p. 1] Zweiter Teil, erste Seite.

[p. 2] Zweiter Teil, zweite Seite.
"""

REPEATING_PAGES = [
    {"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
    {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0},
    {"pos": 9, "label": "1", "source": "catalogue", "confidence": 1.0},
    {"pos": 10, "label": "2", "source": "printed", "confidence": 1.0},
]


def test_a_label_that_repeats_has_no_single_page(tmp_path):
    """A volume in parts restarts its numbering (the corpus has one with five
    pages labelled 1). Asked by label alone, the answer is not one page."""
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(REPEATING_PAGES), body=REPEATING))
    assert b.physical_page_of("1") is None
    assert b.source_of("1") is None


def test_each_marker_finds_its_own_page_in_reading_order(tmp_path):
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(REPEATING_PAGES), body=REPEATING))
    resolved = b.resolve_marks(parse_prepared(b.text))
    assert [(e.pos, e.source) for e in resolved] == [
        (3, "printed"), (4, "printed"), (9, "catalogue"), (10, "printed")]


def test_a_page_without_a_marker_does_not_shift_the_rest(tmp_path):
    # A labelled page with no text of its own gets no marker in the master;
    # the next marker with that label belongs to a later page, not to it.
    body = "[p. 1] Erster Teil.\n\n[p. 1] Zweiter Teil.\n\n[p. 2] Weiter.\n"
    pages = [
        {"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
        {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0},   # leer, ohne Marker
        {"pos": 9, "label": "1", "source": "printed", "confidence": 1.0},
        {"pos": 10, "label": "2", "source": "printed", "confidence": 1.0},
    ]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages), body=body))
    assert [e.pos for e in b.resolve_marks(parse_prepared(b.text))] == [3, 9, 10]


def test_a_marker_the_sidecar_does_not_know_resolves_to_nothing(tmp_path):
    """Book text that looks like a marker -- 'Midrash Tanhuma B 1 [p. 73, ed.
    Buber]' in Josephus -- names no page of this volume. It resolves to None and
    leaves the markers after it untouched."""
    body = "[p. 1] Midrash Tanhuma B 1 [p. 73, ed. Buber], und weiter.\n\n[p. 2] Fort.\n"
    pages = [{"pos": 3, "label": "1", "source": "printed", "confidence": 1.0},
             {"pos": 4, "label": "2", "source": "printed", "confidence": 1.0}]
    b = load_bundle(_bundle(tmp_path, sidecar=_sidecar(pages), body=body))
    resolved = b.resolve_marks(parse_prepared(b.text))
    assert [e.pos if e else None for e in resolved] == [3, None, 4]
