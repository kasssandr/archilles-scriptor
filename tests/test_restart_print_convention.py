from scriptor.reflow.footnotes import note_starts


def test_restart_in_another_print_convention_is_a_line_of_the_note():
    # Goodman p. 5: note 5 breaks after "n." and the next line opens "3) in finding".
    lines = ["4 For Josephus' analysis", "5 I follow T. Rajak (London, 1983), p. 106 n.",
             "3) in finding unduly pessimistic", "story must either be reproduced"]
    assert note_starts(lines, 3) == [(0, 4), (1, 5)]


def test_restart_in_the_same_convention_still_opens_a_note():
    lines = ["12 last note of the chapter", "1 first note of the next"]
    assert note_starts(lines, 3) == [(0, 12), (1, 1)]
