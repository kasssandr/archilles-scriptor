"""Render VolumeReports as a Markdown table (human) and JSON (machines)."""
from __future__ import annotations

import json
from dataclasses import asdict

from scriptor.eval.runner import VolumeReport

_HEADER = ("| Volume | Candidate | Anchor | Handled | Silent damage | Labels "
           "| Wrong | Flag prec. | R3 P/R | Regions |"
           "\n|---|---|---|---|---|---|---|---|---|---|")


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _row(r: VolumeReport) -> str:
    a = r.anchors
    anchored = sum(1 for o in a.outcomes
                   if o.status in ("anchored_exact", "anchored_page"))
    fp = f"{r.flags.flag_precision:.2f}" if r.flags.flag_precision is not None else "—"
    if r.citations.emitted and r.citations.r3_precision is not None:
        cit = f"{r.citations.r3_precision:.2f}/{r.citations.r3_recall:.2f}"
    else:
        cit = "—"
    if r.regions.blocks:
        reg = (f"{_pct(r.regions.exact_recall)} "
               f"({r.regions.blocks_found}/{r.regions.blocks_total})")
    else:
        reg = "—"
    return (f"| {r.volume} | {r.candidate} | {_pct(a.anchor_rate)} "
            f"({anchored}/{len(a.outcomes)}) | {_pct(a.handled_rate)} "
            f"| {_pct(a.silent_damage_rate)} | {_pct(r.labels.label_fidelity)} "
            f"| {r.labels.wrong} | {fp} | {cit} | {reg} |")


def _details(r: VolumeReport) -> list[str]:
    lines = []
    for o in r.anchors.outcomes:
        if o.status != "anchored_exact":
            lines.append(f"- {r.volume}/{r.candidate}: p. {o.truth.page} "
                         f"fn {o.truth.num}: {o.status}")
    lines.extend(_region_details(r))
    return lines


def _region_details(r: VolumeReport) -> list[str]:
    """Name what went wrong. A rate says a region was missed; only the name
    says which vocabulary or closing rule to go and look at."""
    who = f"{r.volume}/{r.candidate}"
    lines = []
    for b in r.regions.blocks:
        if b.named == 0:
            lines.append(f"- {who}: region {b.name} from p. {b.from_page} "
                         f"({b.pages} pages) never named")
        elif b.named < b.pages:
            lines.append(f"- {who}: region {b.name} from p. {b.from_page} "
                         f"named on {b.named} of {b.pages} pages")
    if r.regions.false_apparatus:
        pages = ", ".join(r.regions.false_apparatus[:10])
        more = "" if len(r.regions.false_apparatus) <= 10 else ", …"
        lines.append(f"- {who}: body text inside an apparatus region on "
                     f"{len(r.regions.false_apparatus)} pages: {pages}{more}")
    if r.regions.unmatched_boundaries:
        lines.append(f"- {who}: region boundaries absent from the output: "
                     f"{', '.join(r.regions.unmatched_boundaries)}")
    return lines


_HEADING_HEADER = ("| Volume | Candidate | Placed | Precision | Truncated | Depth "
                   "| Steps | Chapter depth | Deleted | Running heads | False |"
                   "\n|---|---|---|---|---|---|---|---|---|---|---|")
# The rare defects are listed in full; the common ones only begin a list.
_MISSED_SHOWN = 10
_FALSE_SHOWN = 20


def _heading_row(r: VolumeReport) -> str:
    h = r.headings
    truncated = sum(1 for p in h.placed if p.truncated)
    depth = _pct(h.depth_exact / h.placed_count) if h.placed_count else "—"
    steps = _pct(h.steps_kept / h.steps_total) if h.steps_total else "—"
    found = h.chapter_depth_found if h.chapter_depth_found is not None else "—"
    return (f"| {r.volume} | {r.candidate} | {_pct(h.recall)} "
            f"({h.placed_count}/{h.total}) | {_pct(h.precision)} | {truncated} "
            f"| {depth} | {steps} | {found} (truth {h.chapter_level}) "
            f"| {len(h.deleted)} | {len(h.running_in_text)} "
            f"| {len(h.false_headings)} |")


def _heading_title(designator: str, title: str) -> str:
    return f"{designator} {title}".strip()


def _heading_details(r: VolumeReport) -> list[str]:
    """Deleted titles and running heads by name, every one of them: they are
    the defects no reader of the output would notice."""
    who = f"{r.volume}/{r.candidate}"
    h = r.headings
    lines = [f"- {who}: title deleted from p. {t.page}: "
             f"{_heading_title(t.designator, t.title)}" for t in h.deleted]
    lines += [f"- {who}: running head in the text at p. {page}: "
              f"{_heading_title(t.designator, t.title)}" for t, page in h.running_in_text]
    lines += [f"- {who}: heading cut short on p. {p.page}: {p.text}"
              for p in h.placed if p.truncated]
    lines += [f"- {who}: false heading on p. {f.page or '—'}: {f.text}"
              for f in h.false_headings[:_FALSE_SHOWN]]
    if len(h.false_headings) > _FALSE_SHOWN:
        lines.append(f"- {who}: … {len(h.false_headings) - _FALSE_SHOWN} "
                     f"more false headings")
    lines += [f"- {who}: missed on p. {t.page}: {_heading_title(t.designator, t.title)}"
              for t in h.missed[:_MISSED_SHOWN]]
    if len(h.missed) > _MISSED_SHOWN:
        lines.append(f"- {who}: … {len(h.missed) - _MISSED_SHOWN} more missed")
    return lines


def _heading_section(reports: list[VolumeReport]) -> list[str]:
    """Only where a truth declares headings -- the table is optional, and a
    suite without heading truth renders exactly as it did before it existed."""
    measured = [r for r in reports if r.headings.total]
    if not measured:
        return []
    lines = ["", _HEADING_HEADER] + [_heading_row(r) for r in measured] + [""]
    for r in measured:
        lines.extend(_heading_details(r))
    return lines


def render_markdown(reports: list[VolumeReport]) -> str:
    lines = [_HEADER] + [_row(r) for r in reports] + [""]
    for r in reports:
        lines.extend(_details(r))
    lines.extend(_heading_section(reports))
    return "\n".join(lines).rstrip() + "\n"


def render_json(reports: list[VolumeReport]) -> str:
    return json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2)
