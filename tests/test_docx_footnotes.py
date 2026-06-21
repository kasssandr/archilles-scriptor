from docx_helpers import doc_xml, para_xml, run_xml
from scriptor.docx.document import Document
from scriptor.docx.footnotes import collect, assign


def _doc(*paras):
    return Document.from_document_xml(doc_xml(*paras))


def test_collect_finds_refs_and_defs():
    doc = _doc(
        para_xml(run_xml("text"), run_xml("8", superscript=True)),
        para_xml(text="8.) Source eight."),
        para_xml(text="plain prose without notes"),
    )
    refs, defs = collect(doc)
    assert [(r.para_index, r.number) for r in refs] == [(0, 8)]
    assert [(d.para_index, d.number, d.is_attached) for d in defs] == [(1, 8, False)]


def test_assign_simple_pair():
    doc = _doc(
        para_xml(run_xml("a"), run_xml("8", superscript=True)),
        para_xml(text="filler"),
        para_xml(text="8.) Source eight."),
    )
    refs, defs = collect(doc)
    pairs, orphan_defs, orphan_refs = assign(refs, defs)
    assert orphan_defs == [] and orphan_refs == []
    assert [(r.number, d.number) for r, d in pairs] == [(8, 8)]
    assert pairs[0][0].para_index == 0  # an die Referenz in Absatz 0


def test_assign_respects_chapter_number_reset():
    doc = _doc(
        para_xml(run_xml("ch1 "), run_xml("8", superscript=True)),
        para_xml(text="8.) First eight."),
        para_xml(run_xml("ch2 "), run_xml("8", superscript=True)),
        para_xml(text="8.) Second eight."),
    )
    refs, defs = collect(doc)
    pairs, orphan_defs, orphan_refs = assign(refs, defs)
    assert orphan_defs == [] and orphan_refs == []
    # jede Definition zur jeweils vorausgehenden Referenz
    got = sorted((r.para_index, d.para_index) for r, d in pairs)
    assert got == [(0, 1), (2, 3)]


def test_assign_orphan_def_and_orphan_ref():
    doc = _doc(
        para_xml(run_xml("a"), run_xml("8", superscript=True)),   # ref 8, hat def
        para_xml(text="8.) Source eight."),
        para_xml(text="5.) Source five — no reference anywhere."),  # orphan def
        para_xml(run_xml("b"), run_xml("9", superscript=True)),   # orphan ref
    )
    refs, defs = collect(doc)
    pairs, orphan_defs, orphan_refs = assign(refs, defs)
    assert [(r.number, d.number) for r, d in pairs] == [(8, 8)]
    assert [d.number for d in orphan_defs] == [5]
    assert [r.number for r in orphan_refs] == [9]
