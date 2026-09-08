"""Reflow: page text into continuous prose — and the evidence rules it keeps.

A stage states, it does not decide. Every statement travels with its source, its
weight and its reason; the weight is the number of fallible steps between the
page and the statement, and where a source's reliability varies from volume to
volume it is measured on the volume, not assumed. Nothing is destroyed before
the verdict: a reading that triggers a deletion has to be narrow, a reading that
only enters a verdict may be wide. Witnesses whose agreement has a common cause
are not a majority.

Four questions to hold against a line of code, one yes is a violation: Does it
delete or overwrite before every consumer has been asked? Does it decide on one
source while a second one exists or will exist? Does it set a weight that could
be measured on this volume? Does it count agreeing witnesses without asking what
they have in common?

A signal with several producers carries its producer with it -- or it has one.

Three axes speak this today, each in its own words, and their shared vocabulary
is the naming convention for any further one: *source/weight/why* for a single
statement, *informed/attested* for what a verdict rests on, *margin* for how far
ahead the winner stands, *rejected* for what was heard and not believed. See
``pagination/observation.py``, ``confidence.GlyphEvidence`` and
``characters.learn_broken_glyphs``. Nothing is renamed retrospectively.
"""

from scriptor.reflow.core import (
    Page,
    parse_page,
    assign_modes,
    calibrate_threshold,
    render_book,
    main as reflow_main,
)

__all__ = [
    "Page",
    "parse_page",
    "assign_modes",
    "calibrate_threshold",
    "render_book",
    "reflow_main",
]
