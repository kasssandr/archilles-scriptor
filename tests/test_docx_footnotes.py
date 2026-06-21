from docx_helpers import doc_xml, para_xml, run_xml
from scriptor.docx.document import Document
from scriptor.docx.footnotes import collect, assign, bind, ATTACHED_INDENT


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


def test_bind_attaches_definition_after_reference():
    doc = _doc(
        para_xml(run_xml("a"), run_xml("8", superscript=True)),
        para_xml(text="filler"),
        para_xml(text="8.) Source eight."),
    )
    report = bind(doc)
    texts = [p.text for p in doc.paragraphs]
    # Definition steht jetzt direkt hinter der Referenz (Absatz 0)
    assert texts[0].startswith("a")
    assert texts[1] == "8.) Source eight."
    assert texts[2] == "filler"
    assert doc.paragraphs[1].left_indent == ATTACHED_INDENT
    assert report.attached == [(8, 0)]
    assert report.orphan_defs == [] and report.orphan_refs == []


def test_bind_multiple_footnotes_one_paragraph_keep_order():
    doc = _doc(
        para_xml(run_xml("a"), run_xml("8", superscript=True),
                 run_xml(" b"), run_xml("9", superscript=True)),
        para_xml(text="8.) Eight."),
        para_xml(text="9.) Nine."),
    )
    bind(doc)
    texts = [p.text for p in doc.paragraphs]
    assert texts[1] == "8.) Eight."
    assert texts[2] == "9.) Nine."


def test_bind_marks_orphans_visibly():
    doc = _doc(
        para_xml(text="5.) Source five — no reference."),   # orphan def
        para_xml(run_xml("b"), run_xml("9", superscript=True)),   # orphan ref
    )
    report = bind(doc)
    assert "[?FN:5:" in doc.paragraphs[0].text
    assert "[?FN:9:" in doc.paragraphs[1].text
    assert [n for n, _ in report.orphan_defs] == [5]
    assert [n for n, _ in report.orphan_refs] == [9]


def test_bind_is_idempotent():
    src = doc_xml(
        para_xml(run_xml("a"), run_xml("8", superscript=True)),
        para_xml(text="filler"),
        para_xml(text="8.) Source eight."),
        para_xml(run_xml("b"), run_xml("9", superscript=True)),  # orphan ref
    )
    doc1 = Document.from_document_xml(src)
    bind(doc1)
    texts1 = [p.text for p in doc1.paragraphs]
    indents1 = [p.left_indent for p in doc1.paragraphs]

    doc2 = Document.from_document_xml(doc1.to_document_xml())
    rep2 = bind(doc2)
    texts2 = [p.text for p in doc2.paragraphs]
    indents2 = [p.left_indent for p in doc2.paragraphs]

    # Strukturell unverändert (robuster als byte-Vergleich):
    assert texts2 == texts1             # keine doppelten Defs/Flags
    assert indents2 == indents1         # keine doppelte Einrückung
    assert rep2.attached == []          # nichts erneut angehängt
    assert [n for n, _ in rep2.orphan_refs] == [9]  # bleibt korrekt gemeldet
