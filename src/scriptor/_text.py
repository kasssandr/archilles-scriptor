"""Small helpers for phrasing CLI messages and sidecar texts."""

from __future__ import annotations


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    """``1 page`` / ``2 pages`` — number and noun agree in grammatical number.

    Only pass ``plural_form`` when the simple ``+"s"`` doesn't work
    (e.g. ``reference without a definition``).
    """
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural_form or singular + 's'}"
