"""What the pagination tells a reader, and what it tells a machine.

Two channels, one verdict. The JSON is the contract with archilles; the text
report is read beside the book, so it is ordered the way the book is and every
entry carries something the reader can search for -- an internal index is
invisible in a text editor (the convention the footnote report established).
"""

import json

from scriptor.reflow.core import Page
from scriptor.reflow.pagination.report import (
    attested_share,
    inherited_share,
    profile_line,
    render_report,
    render_sidecar,
)
from scriptor.reflow.pagination.verdict import run_verdict


def _page(index, label=None, lines=("Ein Satz auf der Seite.",)):
    return Page(num=-1, body_lines=list(lines), index=index, label_bottom=label)


def _volume():
    pages = [_page(1, "11"), _page(2, "12"), _page(3), _page(4, "14")]
    verdict = run_verdict(pages)
    return pages, verdict


# ── the band-wide figure ─────────────────────────────────────────────

def test_the_share_is_the_pages_that_stated_their_own_number():
    pages, _ = _volume()
    # Three of four printed a folio; the fourth was derived from the sequence.
    assert attested_share(pages) == 0.75


def test_a_volume_nobody_could_read_is_attested_by_nothing():
    pages = [_page(1), _page(2)]
    run_verdict(pages)
    assert attested_share(pages) == 0.0


def test_an_empty_volume_does_not_divide_by_zero():
    assert attested_share([]) == 0.0


def test_the_profile_says_the_edge_and_the_share():
    pages, verdict = _volume()
    line = profile_line(pages, verdict)
    assert "bottom" in line and "75%" in line


def test_a_linked_label_counts_as_attested():
    # One definition of "attested", shared with the confidence: the page printed
    # the number, or a contents line printed it and a reference the file
    # resolves put it here. Josephus and Jesus reads 4 % off its own pages and
    # 32 more from its contents links; calling that volume 4 % attested would
    # understate what is actually known about it.
    pages = [_page(1, "11"), _page(2, "12"), _page(3), _page(4, "14")]
    run_verdict(pages, links={1: [(3, "Kapitel 1 ....... 13")]})
    assert pages[2].label_source == "link"
    assert attested_share(pages) == 1.0


def test_the_profile_of_a_volume_without_pagination_says_so():
    pages = [_page(1), _page(2)]
    verdict = run_verdict(pages)
    assert "no printed pagination" in profile_line(pages, verdict)


def test_the_profile_stays_one_line():
    # It goes into the master's metadata block, which is YAML: a second line
    # would end the value.
    pages, verdict = _volume()
    assert "\n" not in profile_line(pages, verdict)


# ── the machine channel ──────────────────────────────────────────────

def test_the_sidecar_carries_the_plan_as_segments():
    pages, verdict = _volume()
    data = json.loads(render_sidecar(pages, verdict))
    assert data["segments"][0]["start_label"] == "11"
    assert data["segments"][0]["style"] == "arabic"


def test_the_sidecar_carries_every_labelled_position():
    pages, verdict = _volume()
    data = json.loads(render_sidecar(pages, verdict))
    assert [p["pos"] for p in data["pages"]] == [1, 2, 3, 4]
    assert [p["label"] for p in data["pages"]] == ["11", "12", "13", "14"]
    assert data["pages"][2]["source"] == "computed"


def test_the_sidecar_carries_the_confidence_of_each_position():
    pages, verdict = _volume()
    data = json.loads(render_sidecar(pages, verdict))
    assert all(0.0 <= p["confidence"] <= 1.0 for p in data["pages"])


def test_the_sidecar_names_what_was_overruled():
    pages = [_page(1, "11"), _page(2, "12"), _page(3, "2020"), _page(4, "14")]
    verdict = run_verdict(pages)
    data = json.loads(render_sidecar(pages, verdict))
    (rejected,) = data["rejected"]
    assert rejected["label"] == "2020"
    assert rejected["verdict"] == "year"
    assert rejected["predicted"] == "13"


def test_the_sidecar_is_stable_json():
    # It is a file in a repository for whoever keeps one: a rerun that changes
    # nothing must produce no diff.
    pages, verdict = _volume()
    assert render_sidecar(pages, verdict) == render_sidecar(pages, verdict)


def test_the_sidecar_declares_its_own_version():
    pages, verdict = _volume()
    assert json.loads(render_sidecar(pages, verdict))["version"] == 1


# ── the human channel ────────────────────────────────────────────────

def test_the_report_opens_with_what_it_is_about():
    pages, verdict = _volume()
    text = render_report(pages, verdict, "band.md")
    assert "band.md" in text.splitlines()[0]


def test_the_report_states_the_segments():
    pages, verdict = _volume()
    text = render_report(pages, verdict, "band.md")
    assert "arabic" in text


def test_an_overruled_reading_is_reported_with_a_searchable_sample():
    # The reader has the book open, not the page model: "position 3" means
    # nothing to them, the sentence on the page does.
    pages = [_page(1, "11"), _page(2, "12"),
             _page(3, "2020", lines=("Ein Satz, den man suchen kann.",)),
             _page(4, "14")]
    verdict = run_verdict(pages)
    text = render_report(pages, verdict, "band.md")
    assert "2020" in text
    assert "year" in text
    assert "Ein Satz, den man suchen kann." in text


def test_the_report_is_ordered_by_position():
    pages = [_page(1, "2020"), _page(2, "12"), _page(3, "13"),
             _page(4, "1999"), _page(5, "15")]
    verdict = run_verdict(pages)
    lines = [ln for ln in render_report(pages, verdict, "b.md").splitlines()
             if "overruled" not in ln and ("2020" in ln or "1999" in ln)]
    assert lines[0].index("2020") >= 0 and "1999" in lines[1]


def test_a_volume_with_nothing_to_report_still_reports_that():
    pages, verdict = _volume()
    text = render_report(pages, verdict, "band.md")
    assert "0" in text or "none" in text.lower()


# ── text that cites as another page ──────────────────────────────────
#
# A marker addresses all text up to the next one (spec §4.2), and a page with no
# label gets no marker: its text runs on under the last label before it. Neither
# the master nor the sidecar's page list shows that, so the producer has to say
# how much of the volume it is. Measured over thirty library volumes: nineteen
# at zero, the rest mostly below two per cent -- and three at 49 to 89 per cent.

def _labelled(index, label, words=5):
    return Page(num=-1, body_lines=[" ".join(["Wort"] * words)], index=index, label=label)


def _bare(index, words=5, notes=None):
    return Page(num=-1, body_lines=[" ".join(["Wort"] * words)] if words else [],
                footnotes=notes or {}, index=index)


def test_an_unnumbered_page_between_numbered_ones_cites_as_the_one_before():
    pages = [_labelled(1, "11"), _bare(2), _labelled(3, "13")]
    assert inherited_share(pages) == 5 / 15


def test_text_before_the_first_number_has_no_address_rather_than_a_wrong_one():
    pages = [_bare(1, words=20), _labelled(2, "12")]
    assert inherited_share(pages) == 0.0


def test_a_volume_without_any_number_inherits_nothing():
    # Its text has no address at all; the attested share already says so.
    assert inherited_share([_bare(1), _bare(2)]) == 0.0


def test_text_after_the_last_number_cites_as_the_last_one():
    # Niedersachsen: 43 pages after the last number read, all under [p. 576].
    pages = [_labelled(1, "11"), _bare(2), _bare(3)]
    assert inherited_share(pages) == 10 / 15


def test_a_blank_page_carries_no_text_to_misplace():
    pages = [_labelled(1, "11"), _bare(2, words=0), _labelled(3, "13")]
    assert inherited_share(pages) == 0.0


def test_the_notes_of_an_unnumbered_page_cite_with_it():
    # A note takes the address of the paragraph that anchors it.
    pages = [_labelled(1, "11"), _bare(2, words=0, notes={1: "eins zwei drei vier fünf"})]
    assert inherited_share(pages) == 5 / 10


def test_an_empty_volume_inherits_nothing():
    assert inherited_share([]) == 0.0


def test_the_sidecar_says_how_much_text_cites_as_another_page():
    pages, verdict = _volume()
    assert json.loads(render_sidecar(pages, verdict))["profile"]["inherited"] == 0.0
    pages[2].label = None            # as if the sequence could not bridge page 3
    assert json.loads(render_sidecar(pages, verdict))["profile"]["inherited"] == 0.25


def test_the_report_names_each_page_that_cites_as_another_with_a_sample():
    pages, verdict = _volume()
    pages[2].label = None
    pages[2].body_lines = ["Ein Kapitelanfang, den man suchen kann."]
    text = render_report(pages, verdict, "band.md")
    assert "Ein Kapitelanfang, den man suchen kann." in text
    line = next(ln for ln in text.splitlines() if "Kapitelanfang" in ln)
    assert "'12'" in line            # the label its text is cited under


def test_the_report_says_when_every_page_cites_as_itself():
    pages, verdict = _volume()
    text = render_report(pages, verdict, "band.md")
    assert "earlier page's number: 0" in text
