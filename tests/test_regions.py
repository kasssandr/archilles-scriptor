from scriptor.reflow.core import detect_page_number


def test_pure_digit_line_is_page_number():
    assert detect_page_number("146") == 146
    assert detect_page_number("  23 ") == 23


def test_number_with_allcaps_running_head():
    # Braunfels: page number sits at the start of a running-head line.
    assert detect_page_number("146 WILHELM HEIL") == 146
    assert detect_page_number("L'ORIGINE DE LA NOBLESSE 23") == 23


def test_body_number_is_not_a_page_number():
    # Leading year in ordinary prose must NOT be taken as a page number
    # (the trailing text is not running-head-like).
    assert detect_page_number("1990 war ein gutes Jahr fuer die Forschung") is None
    assert detect_page_number("3. Die Probleme um Welf VI. im Vergleich") is None


def test_non_numeric_line_is_none():
    assert detect_page_number("Ein ganz normaler Satz.") is None
    assert detect_page_number("") is None


def test_implausible_number_is_none():
    # 5-digit / zero are not plausible book page numbers.
    assert detect_page_number("12345") is None
    assert detect_page_number("0") is None
