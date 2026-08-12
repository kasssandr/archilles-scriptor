"""Adapters turn candidate output files into one comparable ParsedDoc shape."""
from scriptor.eval.adapters import page_at, parse_prepared, region_at

PREPARED = """[p. xiv] Front text here.

[p. 1] A sentence with an anchor [^1] and a lost marker&[?FN:2|&] plus
another [??FN:3|b:0.7] guessed spot and an orphan[?FN:4] flag [^2]{#a}.

[Aerts 2003, 25]{.cit type=r3 ref=aerts2003} and [Dio Chrys., Or. 36]{.cit type=r4} close.

[^1]: First note text.

[^2]: Fourth note, hanging.
"""


def test_page_marks_in_order():
    doc = parse_prepared(PREPARED)
    assert [lbl for lbl, _ in doc.page_marks] == ["xiv", "1"]
    assert page_at(doc, 0) == ""            # before the first marker
    assert page_at(doc, len(doc.body) - 1) == "1"


def test_footnotes_with_anchor_offsets_and_definitions():
    doc = parse_prepared(PREPARED)
    fns = {f.ident: f for f in doc.footnotes}
    assert fns[1].definition == "First note text."
    assert doc.body[fns[1].anchor_offset:fns[1].anchor_offset + 4] == "[^1]"
    assert fns[2].definition == "Fourth note, hanging."


def test_definition_block_not_in_body():
    doc = parse_prepared(PREPARED)
    assert "First note text." not in doc.body


def test_flags_with_kind_and_printed_number():
    doc = parse_prepared(PREPARED)
    kinds = {(f.fn_num, f.kind) for f in doc.flags}
    assert kinds == {(2, "suggested"), (3, "guessed"), (4, "orphan")}


def test_cit_spans():
    doc = parse_prepared(PREPARED)
    assert (doc.cit_spans[0].text, doc.cit_spans[0].regime,
            doc.cit_spans[0].ref) == ("Aerts 2003, 25", "r3", "aerts2003")
    assert doc.cit_spans[1].regime == "r4" and doc.cit_spans[1].ref is None


from scriptor.eval.adapters import ADAPTERS, parse_plain

XBERG_LIKE = """Some body text where the marker degraded to leaders.4 5 and
the footnote text sits inline as an anonymous block.

4) Fourth note text, long enough to count as a definition line.
5) Fifth note text, also long enough to count here.
217
More prose on the next physical page without any printed label.
"""


def test_plain_adapter_finds_numbered_definition_lines():
    doc = parse_plain(XBERG_LIKE)
    idents = sorted(f.ident for f in doc.footnotes)
    assert idents == [4, 5]
    assert all(f.anchor_offset is None for f in doc.footnotes)


def test_plain_adapter_bare_number_line_is_a_page_mark():
    doc = parse_plain(XBERG_LIKE)
    assert ("217" in [lbl for lbl, _ in doc.page_marks])


def test_plain_adapter_no_flags_no_cits():
    doc = parse_plain(XBERG_LIKE)
    assert doc.flags == [] and doc.cit_spans == []


def test_adapter_registry():
    assert set(ADAPTERS) == {"prepared", "plain"}


# regions (spec §4.4) -------------------------------------------------------

REGIONED = """[region: main]

[p. 300] The last page of the argument.

[region: bibliography]

[p. 301] Aerts, W. J. 2003. Some Title.

[p. 302] Bauer, Eva-Maria. 2020. Another.

[region: index]

[p. 339] Abelard 12, 44
"""


def test_region_marks_are_read_in_order():
    doc = parse_prepared(REGIONED)
    assert [name for name, _ in doc.region_marks] == ["main", "bibliography", "index"]


def test_region_at_follows_the_reach_rule():
    doc = parse_prepared(REGIONED)
    assert region_at(doc, doc.body.index("The last page")) == "main"
    assert region_at(doc, doc.body.index("Aerts, W. J.")) == "bibliography"
    assert region_at(doc, doc.body.index("Abelard")) == "index"


def test_text_before_any_marker_is_in_no_region():
    doc = parse_prepared("[p. 1] Untagged text.\n")
    assert region_at(doc, 5) == ""


def test_region_marker_is_not_left_in_the_body():
    """A snippet search must never match the declaration, only the text."""
    doc = parse_prepared(REGIONED)
    assert "[region:" not in doc.body


def test_region_holds_from_its_own_position():
    """The marker is lifted out, so it occupies no width: the text that took
    its place is already inside the region, not still before it."""
    doc = parse_prepared("[region: index]\n[p. 339] Abelard 12, 44\n")
    assert doc.body.startswith("[p. 339]")
    assert region_at(doc, 0) == "index"
