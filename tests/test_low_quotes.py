"""The low opening quote „ that the OCR read as two commas.

Taubes' Vom Kult zur Kultur prints the misreading some 1500 times, and as often
as not without the space before it: "im Titel,,Surrealismus\"". Two commas
before a word are no punctuation in any language, so the reading is repaired
where the characters are resolved, before anything reads the text -- in a
volume that sets „ at all, which the volume itself has to show.
"""

from scriptor.reflow.characters import MIN_LOW_QUOTES, resolve_characters


def _one(line: str) -> str:
    (out,), _report = resolve_characters([[line]], low_quote=True)
    return out[0]


def test_a_volume_that_prints_the_low_quote_earns_the_reading():
    german = [["Er sprach vom „Kult“."] * MIN_LOW_QUOTES + ['im Titel,,Surrealismus"']]
    (out,), _report = resolve_characters(german)
    assert out[-1] == 'im Titel „Surrealismus"'


def test_a_volume_that_never_prints_it_keeps_its_commas():
    # The Chaldaean Oracles: English, no „ anywhere, double commas as debris.
    english = [["compared by LUCRETIUS, I, 900,,,llammai... flore\""]]
    (out,), report = resolve_characters(english)
    assert out == english[0]
    assert report.low_quotes == 0


def test_two_commas_before_a_word_are_the_low_quote():
    assert _one('die Frage,,Was können wir wissen?"') == 'die Frage „Was können wir wissen?"'


def test_the_quote_at_a_line_start_needs_no_space():
    assert _one(',,die moderne Theologie"') == '„die moderne Theologie"'


def test_after_a_space_or_a_colon_the_quote_keeps_its_place():
    assert _one('schloß:,,Er ist') == 'schloß: „Er ist'
    assert _one('sagt ,,nein"') == 'sagt „nein"'


def test_three_commas_are_a_comma_and_the_quote():
    assert _one('herangezogen,,,die ihn') == 'herangezogen, „die ihn'


def test_a_compound_hyphen_joins_the_quote_a_dash_stands_apart():
    assert _one('Anti-,,Gesetz"') == 'Anti-„Gesetz"'
    assert _one('Johannesevangelium -,,denn') == 'Johannesevangelium - „denn'


def test_a_comma_after_the_quote_goes():
    assert _one('gegen die „,Kultur“ ausspielen') == 'gegen die „Kultur“ ausspielen'


def test_two_commas_before_a_space_are_left_alone():
    # Nothing says what they were.
    assert _one('Der Apokalyptiker,, weiß') == 'Der Apokalyptiker,, weiß'


def test_the_report_counts_the_quotes():
    _out, report = resolve_characters([['im Titel,,Surrealismus" und,,Kunst"']],
                                      low_quote=True)
    assert report.low_quotes == 2
