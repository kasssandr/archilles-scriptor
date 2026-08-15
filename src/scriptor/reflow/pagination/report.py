"""What the pagination says, for a reader and for a machine.

Two channels out of one verdict, and they answer different questions.

The **sidecar** (`pagination.json`) is the contract with archilles: the plan as a
table of segments, every position with its label, source and confidence, and the
readings the sequence overruled. It exists because the Markdown master is a
view -- a label travels into it as ``[p. NN]`` and everything the consensus knew
about that label is gone (KONZEPT_scriptor_v2 §9 Q1: a decision sidecar, not a
round trip).

The **report** is read beside the book. It is therefore ordered the way the book
is, and every entry carries a sentence the reader can search for: an internal
position is invisible in a text editor, which is the convention the footnote
report established.
"""

from __future__ import annotations

import json

from scriptor.reflow.pagination.rejected import classify

SIDECAR_VERSION = 1

# How much of a page's text to quote so the reader can find it again. Long
# enough to be unique in a volume, short enough to stay on one line beside the
# rest of the entry.
SAMPLE_CHARS = 60


def attested_share(pages) -> float:
    """The share of positions whose label the page itself stated.

    This is the number archilles asks when it wants to know whether the page
    references of this volume can be trusted (design §7.2). Not the share of
    labelled pages: a volume can be labelled throughout by counting from a
    single reading, and that is a different thing from a volume that prints its
    folios.
    """
    if not pages:
        return 0.0
    printed = sum(1 for p in pages if p.label_source == "printed")
    return printed / len(pages)


def profile_line(pages, verdict) -> str:
    """The volume's pagination in one line, for the master's metadata block.

    One line because the block is YAML and a second one would end the value.
    """
    share = attested_share(pages)
    edge = verdict.description if verdict.description in ("top", "bottom") else None
    if edge is None and verdict.band is not None:
        edge = verdict.band.edge
    where = f"{edge} edge" if edge else "no printed pagination"
    return f"{where}, {share:.0%} of pages attested in print"


def _sample(page) -> str:
    """A line of the page a reader can search for."""
    if page is None:
        return ""
    text = next((ln.strip() for ln in page.body_lines if ln.strip()), "")
    return text[:SAMPLE_CHARS]


def _rejections(pages, verdict):
    by_pos = {p.index: p for p in pages}
    return classify(verdict.rejected, by_pos, verdict.plan), by_pos


def render_sidecar(pages, verdict) -> str:
    """The machine channel: stable JSON, so a rerun that changes nothing
    produces no diff."""
    rejections, by_pos = _rejections(pages, verdict)
    payload = {
        "version": SIDECAR_VERSION,
        "profile": {
            "edge": None if verdict.band is None else verdict.band.edge,
            "band": (None if verdict.band is None
                     else [round(verdict.band.lo, 4), round(verdict.band.hi, 4)]),
            "attested": round(attested_share(pages), 4),
            "description": verdict.description,
        },
        "segments": [
            {"start_pos": s.start_pos, "start_label": s.start_label,
             "style": s.style, "kind": s.kind}
            for s in verdict.plan.segments
        ],
        "pages": [
            {"pos": p.index, "label": p.label, "source": p.label_source,
             "confidence": (None if p.label_confidence is None
                            else round(p.label_confidence, 4))}
            for p in sorted(pages, key=lambda p: p.index)
            if p.label is not None
        ],
        "rejected": [
            {"pos": r.observation.pos, "label": r.observation.label,
             "source": r.observation.source, "verdict": r.verdict,
             "predicted": r.predicted, "why": r.observation.why,
             "sample": _sample(by_pos.get(r.observation.pos))}
            for r in rejections
        ],
    }
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def render_report(pages, verdict, out_path: str) -> str:
    """The human channel: what the volume is paginated like, and what was
    overruled to get there."""
    rejections, by_pos = _rejections(pages, verdict)
    labelled = sum(1 for p in pages if p.label is not None)
    printed = sum(1 for p in pages if p.label_source == "printed")

    lines = [
        f"# Pagination of {out_path}",
        f"# {len(pages)} pages, {labelled} labelled, {printed} of them read off "
        f"the page itself ({attested_share(pages):.0%}).",
        f"# Profile: {profile_line(pages, verdict)}.",
    ]
    if verdict.band is not None:
        lines.append(
            f"# Folios sit at {verdict.band.lo:.3f}-{verdict.band.hi:.3f} of the "
            f"page height; {verdict.geometric_count} were read there in a second pass."
        )
    lines += [
        "# Sources: printed = the page states it, catalogue = the PDF's own",
        "# PageLabels, toc = the table of contents names it, computed = it",
        "# follows from the sequence and nobody observed it.",
        "",
        "## Segments",
    ]
    for s in verdict.plan.segments:
        kind = "" if s.kind == "counted" else f"  [{s.kind}]"
        lines.append(
            f"  from page {s.start_pos:>4}   {s.style:<12} starting at "
            f"{s.start_label}{kind}"
        )

    lines += ["", f"## Readings the sequence overruled: {len(rejections)}"]
    if not rejections:
        lines.append("  none — every reading fits the plan")
    for r in rejections:
        predicted = r.predicted or "nothing"
        lines.append(
            f"  page {r.observation.pos:>4}  read {r.observation.label!r:<10} "
            f"[{r.verdict}]  the plan states {predicted!r}"
        )
        lines.append(
            f"            {r.observation.source} · {_sample(by_pos.get(r.observation.pos))!r}"
        )

    low = [p for p in sorted(pages, key=lambda p: p.index)
           if p.label is not None and p.label_confidence is not None
           and p.label_confidence < 0.5]
    lines += [
        "",
        f"## Labels the consensus is least sure of: {len(low)}",
        "# Confidence measures corroboration, not legibility: a page that prints"
        " its",
        "# own folio still scores low where its stretch is short, because there"
        " is",
        "# little for it to agree with. A volume with no printed folio anywhere"
        " scores",
        "# zero throughout — that is the honest answer, not a fault of the page.",
    ]
    if not low:
        lines.append("  none below 0.5")
    for p in low[:40]:
        lines.append(
            f"  page {p.index:>4}  {p.label!r:<10} {p.label_source:<10} "
            f"{p.label_confidence:.2f}  {_sample(p)!r}"
        )
    return "\n".join(lines) + "\n"
