import pytest

from scriptor.page import Box, Line, Span, SourcePage, dumps, load_pages, page_from_text


def test_text_page_becomes_one_span_per_line_without_geometry():
    page = page_from_text(3, "first line\n\nthird line\n")
    assert [line.text for line in page.lines] == ["first line", "", "third line"]
    assert all(line.box is None and line.baseline is None for line in page.lines)
    assert page.index == 3
    assert page.source == "text"


def test_load_pages_reads_json_in_page_order(tmp_path):
    for i in (2, 1, 10):
        page = SourcePage(index=i, source="pymupdf",
                          lines=[Line(spans=[Span(f"page {i}", box=Box(0, 0, 1, 1))],
                                      box=Box(0, 0, 1, 1), baseline=0.8)])
        (tmp_path / f"{i:08d}.json").write_text(dumps(page), encoding="utf-8")

    pages = load_pages(tmp_path)

    assert [p.index for p in pages] == [1, 2, 10]
    assert pages[0].lines[0].baseline == 0.8


def test_load_pages_lifts_a_txt_directory(tmp_path):
    (tmp_path / "00000001.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    (tmp_path / "00000002.txt").write_text("gamma\n", encoding="utf-8")

    pages = load_pages(tmp_path)

    assert [p.index for p in pages] == [1, 2]
    assert [line.text for line in pages[0].lines] == ["alpha", "beta"]
    assert pages[0].lines[0].box is None


def test_load_pages_refuses_both_formats_for_the_same_page(tmp_path):
    (tmp_path / "00000001.json").write_text(dumps(SourcePage(index=1)), encoding="utf-8")
    (tmp_path / "00000001.txt").write_text("alpha\n", encoding="utf-8")

    with pytest.raises(ValueError, match="00000001"):
        load_pages(tmp_path)


def test_emitted_txt_subdirectory_is_not_read(tmp_path):
    (tmp_path / "00000001.json").write_text(dumps(SourcePage(index=1)), encoding="utf-8")
    (tmp_path / "txt").mkdir()
    (tmp_path / "txt" / "00000001.txt").write_text("alpha\n", encoding="utf-8")

    assert [p.index for p in load_pages(tmp_path)] == [1]


def test_an_empty_directory_yields_no_pages(tmp_path):
    assert load_pages(tmp_path) == []
