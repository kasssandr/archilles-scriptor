"""One witness's statement about one page. Nothing else lives here.

A witness says: at this position the volume prints this label, and here is how
much that statement is worth. Whether the statement is true is not the witness's
business -- that is settled by the plan which explains the most of them
(``plan.fit``).

``why`` is carried through to the audit unchanged. A verdict nobody can read
back is a guess with better manners.

The rule this is one instance of -- a stage states, it does not decide -- is
written out once in ``scriptor.reflow`` (module docstring), and the names
``source``/``weight``/``why`` are the convention any further axis follows.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    pos: int        # positional page index (Page.index), 1-based
    label: str      # the claimed label, verbatim ("xiv", "312")
    source: str     # "printed-top" | "printed-bottom" | "catalogue" | ...
    weight: float
    why: str
