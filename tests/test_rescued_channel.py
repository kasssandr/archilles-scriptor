"""Der eine Kanal, in den die Stripper ihre geborgenen Folios legen.

Vier Stufen greifen in eine Zeile, die sie gleich löschen, und behalten die
Zahl, die darin stand. Sie gaben das als vier parallele Listen zurück, die
``reflow.core`` wieder zusammennähte — vier Kanäle für eine Sache, und die
Zusammenführung eine Stelle, an der etwas aus dem Tritt geraten kann. Jetzt
*ergänzen* alle vier denselben Record.
"""

import pytest

from scriptor.reflow.rescued import RescuedFolios


def test_an_empty_channel_says_nothing():
    assert RescuedFolios(5).by_position() == {}
    assert len(RescuedFolios(5)) == 0


def test_positions_are_physical_pages_and_count_from_one():
    rescued = RescuedFolios(3)
    rescued.add(0, "top", "146")
    assert rescued.by_position() == {1: [("top", "146")]}


def test_a_line_without_a_number_is_the_ordinary_case():
    # Most removed furniture carries no folio. That is not an error to refuse,
    # it is what a stripper hands over on nearly every page.
    rescued = RescuedFolios(2)
    rescued.add(0, "top", None)
    assert rescued.by_position() == {}


def test_both_edges_of_one_page_may_speak():
    rescued = RescuedFolios(1)
    rescued.add(0, "bottom", "9")
    rescued.add(0, "top", "146")
    assert rescued.by_position() == {1: [("top", "146"), ("bottom", "9")]}


def test_two_heads_on_one_page_are_two_statements():
    # Josephus and Jesus: a download banner ending in the year, and the
    # chapter's running head ending in the folio.
    rescued = RescuedFolios(1)
    rescued.add(0, "top", "2025")
    rescued.add(0, "top", "113")
    assert rescued.by_position() == {1: [("top", "2025"), ("top", "113")]}


def test_the_same_number_at_one_edge_is_one_statement():
    rescued = RescuedFolios(1)
    rescued.add(0, "top", "146")
    rescued.add(0, "top", "146")
    assert rescued.by_position() == {1: [("top", "146")]}


def test_an_edge_is_top_or_bottom():
    with pytest.raises(ValueError):
        RescuedFolios(1).add(0, "left", "146")


def test_the_channel_survives_every_stripper_in_order():
    """What core.main does: three stages add to one record, and the consensus
    reads it once. The order of the stages does not have to be tracked by
    anyone -- that is the point of the channel."""
    from scriptor.reflow.outline import strip_running_titles
    from scriptor.reflow.running_elements import (
        remove_running_footers_from_blocks,
        strip_running_elements,
    )

    title = "Die Uebergabe von Narbonne an die Franken"
    pages_lines = [
        [f"{40 + i} {title}", f"Text der Seite {i} steht hier und laeuft weiter."]
        for i in range(4)
    ]
    rescued = RescuedFolios(len(pages_lines))
    pages_lines, contested = strip_running_titles(pages_lines, [title], rescued)
    assert contested == 0
    assert all(title not in "\n".join(lines) for lines in pages_lines)

    texts = ["\n".join(lines) for lines in pages_lines]
    strip_running_elements(texts, rescued)
    remove_running_footers_from_blocks([None] * len(texts), [], rescued)

    assert rescued.by_position() == {
        i: [("top", str(39 + i))] for i in range(1, 5)
    }
