from scriptor.pages_zip import natural_sort_key, is_page_file, decode_bytes


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
