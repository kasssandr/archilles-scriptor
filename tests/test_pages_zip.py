import zipfile
from pathlib import Path

from scriptor.pages_zip import natural_sort_key, is_page_file, decode_bytes, collect_page_texts, convert, PagesZipResult


def test_natural_sort_orders_page_9_before_page_10():
    names = ["page_10.txt", "page_9.txt", "page_1.txt"]
    assert sorted(names, key=natural_sort_key) == [
        "page_1.txt",
        "page_9.txt",
        "page_10.txt",
    ]


def test_natural_sort_handles_zero_padded_and_mixed_schemes():
    names = ["leaf_0012.txt", "leaf_0002.txt", "0001.txt"]
    assert sorted(names, key=natural_sort_key) == [
        "0001.txt",
        "leaf_0002.txt",
        "leaf_0012.txt",
    ]


def test_is_page_file_keeps_numbered_txt():
    assert is_page_file("00000007.txt") is True
    assert is_page_file("book_id/page_12.txt") is True


def test_is_page_file_skips_non_txt_and_artifacts():
    assert is_page_file("cover.jpg") is False
    assert is_page_file("book_djvu.xml") is False
    assert is_page_file("__ia_thumb.jpg") is False
    assert is_page_file("__MACOSX/._00000001.txt") is False
    assert is_page_file("metadata.txt") is False


def test_decode_bytes_utf8_fast_path():
    text, used_fallback = decode_bytes("Köln — Anmerkung".encode("utf-8"))
    assert text == "Köln — Anmerkung"
    assert used_fallback is False


def test_decode_bytes_latin1_fallback():
    # 0xFC is 'ü' in latin-1 but invalid as a standalone UTF-8 byte.
    raw = "Fußnote".encode("latin-1")
    text, used_fallback = decode_bytes(raw)
    assert "Fu" in text and "note" in text
    assert used_fallback is True


def _make_zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    zip_path = tmp_path / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return zip_path


def test_collect_orders_pages_and_drops_artifacts(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "book/page_10.txt": b"ten",
            "book/page_2.txt": b"two",
            "book/page_1.txt": b"one",
            "book/__ia_thumb.jpg": b"\xff\xd8\xff",
            "book/book_djvu.xml": b"<xml/>",
        },
    )
    pages, skipped, fallbacks = collect_page_texts(zip_path)
    assert [text for _, text in pages] == ["one", "two", "ten"]
    assert any("thumb" in s for s in skipped)
    assert any(".xml" in s for s in skipped)
    assert fallbacks == 0


def test_collect_from_directory(tmp_path):
    d = tmp_path / "pages"
    d.mkdir()
    (d / "00000002.txt").write_text("b", encoding="utf-8")
    (d / "00000001.txt").write_text("a", encoding="utf-8")
    pages, skipped, fallbacks = collect_page_texts(d)
    assert [text for _, text in pages] == ["a", "b"]


def test_collect_counts_encoding_fallbacks(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {"0001.txt": "Fußnote".encode("latin-1"), "0002.txt": b"plain"},
    )
    pages, skipped, fallbacks = collect_page_texts(zip_path)
    assert fallbacks == 1


def test_convert_writes_zero_padded_pages(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {"page_2.txt": b"two", "page_1.txt": b"one", "cover.jpg": b"\xff"},
    )
    out_dir = tmp_path / "out_pages"
    result = convert(zip_path, out_dir)
    assert isinstance(result, PagesZipResult)
    assert (out_dir / "00000001.txt").read_text(encoding="utf-8") == "one"
    assert (out_dir / "00000002.txt").read_text(encoding="utf-8") == "two"
    assert result.pages_dir == out_dir
    assert len(result.kept) == 2
    assert any("cover" in s for s in result.skipped)


def test_convert_dry_run_writes_nothing(tmp_path):
    zip_path = _make_zip(tmp_path, {"0001.txt": b"a", "0002.txt": b"b"})
    result = convert(zip_path, None, dry_run=True)
    assert result.pages_dir is None
    assert len(result.kept) == 2
    # No pages dir created anywhere under tmp_path.
    assert list(tmp_path.glob("*_pages")) == []


def test_convert_requires_pages_dir_when_not_dry_run(tmp_path):
    import pytest

    zip_path = _make_zip(tmp_path, {"0001.txt": b"a"})
    with pytest.raises(ValueError):
        convert(zip_path, None, dry_run=False)


from scriptor.cli import main as cli_main


def _make_reflowable_zip(tmp_path: Path) -> Path:
    # Two minimal pages with a numeric page-number line so the reflow
    # produces non-empty output.
    return _make_zip(
        tmp_path,
        {
            "p_1.txt": "Erster Absatz der ersten Seite.\n1\n".encode("utf-8"),
            "p_2.txt": "Zweiter Absatz der zweiten Seite.\n2\n".encode("utf-8"),
        },
    )


def test_cli_split_only_writes_pages_dir(tmp_path):
    zip_path = _make_reflowable_zip(tmp_path)
    pages_dir = tmp_path / "pages"
    rc = cli_main(["pages-zip", str(zip_path), "--pages-dir", str(pages_dir)])
    assert rc == 0
    assert (pages_dir / "00000001.txt").exists()
    assert (pages_dir / "00000002.txt").exists()


def test_cli_with_out_produces_markdown(tmp_path):
    zip_path = _make_reflowable_zip(tmp_path)
    out_md = tmp_path / "book.md"
    rc = cli_main(
        ["pages-zip", str(zip_path), "--out", str(out_md), "--pages-dir", str(tmp_path / "pages")]
    )
    assert rc == 0
    assert out_md.exists()
    assert out_md.read_text(encoding="utf-8").strip() != ""


def test_cli_dry_run_writes_nothing(tmp_path):
    zip_path = _make_reflowable_zip(tmp_path)
    rc = cli_main(["pages-zip", str(zip_path), "--dry-run"])
    assert rc == 0
    assert list(tmp_path.glob("*_pages")) == []
    assert not (tmp_path / "book.md").exists()
