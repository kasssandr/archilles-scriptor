"""Authoring aid for ground truth.

This module prepares material for a human: page images, raw text to copy
from, and an empty truth.toml skeleton. It deliberately contributes no
judgement of its own — no detected footnotes, no guessed anchors, nothing
from reflow. Truth is written against the printed page, so that the
benchmark cannot end up measuring how well Scriptor agrees with itself.

It is not part of the measuring path and may therefore use pymupdf, which
the metric modules must not.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PageRef:
    """One physical page and the label its catalogue prints for it."""
    index: int      # 1-based file ordinal
    label: str      # printed label, always a string ("xiv", "14")


def choose_pages(
    refs: list[PageRef], body_range: tuple[int, int], count: int, seed: int
) -> list[str]:
    """Draw `count` page labels from the body range, reproducibly.

    The body range is the operator's documented decision about where running
    text begins and ends; guessing it would mean sorting registers and blank
    pages by heuristic, which is exactly the kind of judgement this module
    must not make. Returns labels in printed order.
    """
    first, last = body_range
    pool = [r for r in refs if first <= r.index <= last]
    if count > len(pool):
        raise ValueError(
            f"asked for {count} pages but the body range holds only {len(pool)}"
        )
    picked = random.Random(seed).sample(pool, count)
    picked.sort(key=lambda r: r.index)
    return [r.label for r in picked]
