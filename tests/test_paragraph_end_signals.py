"""What a short line has to end on to end a paragraph.

Found in Archillator (js/paragraphs.js), which reads pasted PDF text with this
module's rule and met two volumes it could not split: Gregory's *Byzantium*,
an endnote volume whose paragraphs nearly all close on a note number nobody
placed ("as “Belgian Rome.”2"), and Mazzarino's preface, where a closing
guillemet with no stop before it ended a paragraph mid-sentence ("si suole
chiamare «la caduta »" / "e che è, piuttosto"). Gregory came out of the reflow
as three paragraphs; ten were printed.
"""

from scriptor.reflow.core import SENT_END, Page, reconstruct_body


def _paras(lines, threshold=60):
    page = Page(num=-1, index=1, mode="main", label=None, body_lines=list(lines))
    paras, _f, _o, _l = reconstruct_body([page], threshold=threshold)
    return paras


FULL = "Other cities in which emperors had spent more time could instead be"


def test_a_note_number_behind_the_stop_still_ends_the_paragraph():
    paras = _paras([FULL, "imagined to have become “Belgian Rome.”2",
                    FULL, "imagined to have become a ghost town.5",
                    "The Ostrogoths eventually wore out their welcome."])
    assert len(paras) == 3
    assert paras[0].endswith("“Belgian Rome.”2")   # the number stays in the text


def test_a_number_in_the_sentence_is_no_note():
    # No stop before it: "in 410" is the year, and the sentence runs on.
    paras = _paras([FULL, "sacked by the Visigoths in 410", "and by the Vandals in 455."])
    assert len(paras) == 1


def test_a_closing_quote_without_a_stop_ends_no_sentence():
    assert not SENT_END.search("si suole chiamare «la caduta »")
    assert not SENT_END.search("known as “New Rome,”")
    paras = _paras([FULL, "known as “New Rome,”", "“Young Rome.” The fates of Rome."])
    assert len(paras) == 1


def test_a_closing_quote_behind_the_stop_ends_the_sentence():
    for line in ("characterized as “old.”", "sich selbst offenbar machen.\"",
                 "zusammenschmelzen.«", "der Königssalbung.“", "Ebd., S. 18. \"\""):
        assert SENT_END.search(line), line


def test_a_title_on_a_closing_quote_stays_its_own_paragraph():
    # Fried, Donation of Constantine: the old rule took any quote for an end,
    # and only that kept the title off the text below it.
    paras = _paras(["IV. The wording of the “Constitutum Constantini”",
                    FULL, "imagined to have become a ghost town."])
    assert len(paras) == 2
    assert paras[0].endswith("“Constitutum Constantini”")


def test_a_title_over_two_short_lines_stays_its_own_paragraph():
    paras = _paras(["The early tradition in the context of", "the “Constitutum Constantini”",
                    FULL, "imagined to have become a ghost town."])
    assert len(paras) == 2


def test_a_number_with_a_thousands_point_is_no_note():
    # Bauer: "für 90.000" / "bis 100.000 USD" is one sentence.
    paras = _paras([FULL, "bei der Frieze Art Fair 2005 für 90.000",
                    "bis 100.000 USD je Druck verkauft."])
    assert len(paras) == 1
