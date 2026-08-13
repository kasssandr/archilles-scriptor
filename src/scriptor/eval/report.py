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


def render_markdown(reports: list[VolumeReport]) -> str:
    lines = [_HEADER] + [_row(r) for r in reports] + [""]
    for r in reports:
        lines.extend(_details(r))
    return "\n".join(lines).rstrip() + "\n"


def render_json(reports: list[VolumeReport]) -> str:
    return json.dumps([asdict(r) for r in reports], ensure_ascii=False, indent=2)
