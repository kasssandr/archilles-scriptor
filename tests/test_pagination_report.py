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
