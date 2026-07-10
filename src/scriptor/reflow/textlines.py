"""Printed lines, assembled from the line fragments a backend reports.

A ``Line`` is what the backend saw, not what the typesetter set. Google Books splits
one printed line into several fragments; LuraDocument hands over one fragment per
word. Measured on five sample pages each: Seeck reports 731 lines where 216 are
printed, Origenes 363 for 183, Thil-Lorrain 162 for 130. Only Berliner and Josephus
arrive whole.

Downstream, ``calibrate_threshold`` builds its histogram from line lengths and
``is_prose_page`` measures the dominant width against them. Fed fragments of length
5, 26, 5 and 6, both produce plausible-looking, wrong paragraphs -- and say nothing
about it. Reassembling the printed line is therefore the first thing geometry buys.

**The baseline is the anchor, not the box.** Within one printed line of Seeck p.120
the box top scatters by 2.2 points -- ``'falls'`` at 92.97 against ``'sich'`` at
90.77, because ``falls`` has no ascender -- while the baseline scatters by 0.36.
Clustering on the box tears Seeck into 50 lines where 37 are printed, and leaves
Josephus entirely unclustered (43 for 34).

Columns are not resolved here. Joining across a column gap would be a judgement
about reading order that this module has no basis for. It counts the lines with a
suspiciously wide gap so the caller can say so out loud.
"""

from __future__ import annotations

from dataclasses import dataclass

from scriptor.page import Line, SourcePage

# Points. Fragments of one printed line scatter by ~0.4pt on the baseline. Two
# points is already too generous: on the baseline it merges two real lines of Seeck
# (35 clusters where 37 are printed).
BASELINE_TOLERANCE = 1.0

# A horizontal gap this wide, relative to the page, is more likely a column boundary
# than a word space. The topmost and bottommost printed lines are exempt: a running
# head and its folio gape 84pt at 332pt page width in Zuckerman -- 25.3 % -- and
# that is not a column break.
WIDE_GAP_FRACTION = 0.33


@dataclass
class Reconstruction:
    lines: list[str]
    measured: bool          # True: assembled from baselines. False: passed through.
    wide_gap_lines: int     # printed lines holding a suspiciously wide gap
    sizes: list[float | None] = None  # dominant size per printed line, parallel to ``lines``

    def __post_init__(self) -> None:
        if self.sizes is None:
            self.sizes = [None] * len(self.lines)


def _passthrough(page: SourcePage) -> Reconstruction:
    return Reconstruction(
        lines=[line.text for line in page.lines],
        measured=False,
        wide_gap_lines=0,
        sizes=[line.size for line in page.lines],
    )


def _cluster_size(cluster: list[Line]) -> float | None:
    """The dominant size of a printed line, weighted by character count.

    Same rule as ``Line.size``, applied across the fragments of one cluster: a
    short bold run must not drag the whole line to its size. Ties go to the
    larger size, so the result does not depend on iteration order.
    """
    weights: dict[float, int] = {}
    for line in cluster:
        for span in line.spans:
            if span.size is None:
                continue
            weights[span.size] = weights.get(span.size, 0) + len(span.text)
    if not weights:
        return None
    return max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _has_wide_gap(cluster: list[Line], threshold: float) -> bool:
    return any(
        b.box.x0 - a.box.x1 > threshold for a, b in zip(cluster, cluster[1:])
    )


def reconstruct(
    page: SourcePage, *, tolerance: float = BASELINE_TOLERANCE
) -> Reconstruction:
    """Group the fragments of ``page`` into printed lines."""
    if not page.lines:
        return _passthrough(page)
    if any(line.baseline is None or line.box is None for line in page.lines):
        # A half-measured page stays untouched: sorting the lines that do carry a
        # baseline would move the ones that do not to an arbitrary place.
        return _passthrough(page)

    ordered = sorted(page.lines, key=lambda line: (line.baseline, line.box.x0))

    clusters: list[list[Line]] = []
    for line in ordered:
        if clusters and line.baseline - clusters[-1][0].baseline <= tolerance:
            clusters[-1].append(line)
        else:
            clusters.append([line])

    for cluster in clusters:
        cluster.sort(key=lambda line: line.box.x0)

    threshold = (page.width or 0.0) * WIDE_GAP_FRACTION
    inner = clusters[1:-1] if len(clusters) > 2 else []
    wide_gap_lines = (
        sum(1 for cluster in inner if _has_wide_gap(cluster, threshold))
        if threshold
        else 0
    )

    return Reconstruction(
        lines=[" ".join(line.text for line in cluster) for cluster in clusters],
        measured=True,
        wide_gap_lines=wide_gap_lines,
        sizes=[_cluster_size(cluster) for cluster in clusters],
    )
