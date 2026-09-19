"""Offset-preserving text normalization -- it lives in ``scriptor.document``.

The match that finds a snippet again after a line break, a soft hyphen or an
OCR variant is the match an address is resolved with (P-B1), and an address is
read by consumers, which may not import from the benchmark's workshop. So it
moved to the reader of the format, the way ``parse_prepared`` did before it,
and the metrics read it from there rather than keeping a second copy.
"""
from __future__ import annotations

from scriptor.document import (  # noqa: F401 -- the metrics import these from here
    _normalized_with_map,
    find_snippet,
    normalize,
)
