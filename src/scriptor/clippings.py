"""Convert Cambridge-Core / JSTOR / Traditio-style Markdown clippings.

These exports use inline footnote markers (a number written immediately
after a word, no whitespace) and footnote definitions formatted as
``<sup>N</sup> Text … [Google Scholar](URL)``. We rewrite both into
Pandoc footnote syntax (``[^N]`` in body, ``[^N]: Text …`` at the end)
so the document can be processed downstream like any other Pandoc input —
in particular by translation tools that need to preserve bibliographic
references verbatim while translating only the surrounding prose.

Strategy
--------

Body markers are resolved with an **n+1 sequence constraint**: we walk
through the footnote numbers in order ``[1, 2, 3, …]`` and, for each ``n``,
search forward in the body for the next position where ``n`` appears
attached to a word. This makes the conversion robust against false
positives (years like ``1798``, scripture references like ``Gen. 16:1-6``,
parenthetical numbers like ``(d. ca. 220)``): such numbers may match the
naive pattern, but the search position only advances *past* a confirmed
real marker, so a stray digit before the real ``[^n]`` location is
matched only if the real one is missing — in which case we record the
miss and move on without disturbing later numbers.

The matching pattern itself is also conservative: a digit qualifies as a
footnote marker only when preceded by a letter or sentence-ending
punctuation (``. , ; : ! ?  ) ] " ' »`` plus extended Latin letters) and
not followed by another digit. Hyphens, opening brackets and digits are
*not* allowed as the preceding character — that rules out range
constructs like ``1-6`` and most multi-segment scripture references.

Output
------

A sidecar Markdown file alongside the input (``<name>.pandoc.md``) plus
an audit dict for the CLI to render. Existing frontmatter is preserved;
``updated`` is refreshed to today and a ``pandoc_compatible: true`` flag
is added so the next consumer can recognise the converted form. Google
Scholar links inside footnote definitions are kept verbatim — they ride
on the ``[^N]: …`` line and survive Pandoc round-trips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ── Frontmatter (YAML between leading --- markers) ────────────────────
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

# ── Footnote definition: line starts with <sup>N</sup> followed by text.
# The body of a definition continues until the next <sup>M</sup> at line
# start or end-of-file. We match line-anchored to be unambiguous.
_FN_DEF_LINE_RE = re.compile(r"^<sup>(\d+)</sup>\s*(.*)$", re.MULTILINE)

# Body marker: a digit attached to the end of a word.
# Pre-char: ASCII/extended-Latin letter, or sentence-ending punctuation.
# Explicitly excluded from pre-char: whitespace, digit, hyphen, opening
# brackets — those are the surfaces of years, ranges, scripture
# references and parenthetical numbers. The n is filled per-iteration.
_PRE_CHARS = r"a-zA-ZÀ-ſ\.\,\;\:\!\?\)\]\"“”'‘’»"


@dataclass
class ConversionResult:
    text: str
    total_fn_defs: int
    converted_in_body: int
    missing_in_body: list[int] = field(default_factory=list)
    extra_in_body: list[int] = field(default_factory=list)  # numbers found > total_fn_defs

    @property
    def ok(self) -> bool:
        return not self.missing_in_body and not self.extra_in_body


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block_with_delims, rest)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return text[: m.end()], text[m.end() :]


def _update_frontmatter(fm_block: str) -> str:
    """Refresh ``updated:`` to today; add ``pandoc_compatible: true`` if absent.

    The block includes the surrounding ``---`` markers. We rewrite line by
    line to keep ordering and arbitrary keys intact, only touching the
    two fields we manage.
    """
    if not fm_block:
        # No frontmatter present — synthesise a minimal one
        today = date.today().isoformat()
        return (
            "---\n"
            f"updated: {today}\n"
            "pandoc_compatible: true\n"
            "---\n"
        )

    today = date.today().isoformat()
    lines = fm_block.splitlines()
    has_updated = False
    has_compat = False
    out_lines: list[str] = []
    for ln in lines:
        if re.match(r"^updated\s*:", ln):
            out_lines.append(f"updated: {today}")
            has_updated = True
        elif re.match(r"^pandoc_compatible\s*:", ln):
            out_lines.append("pandoc_compatible: true")
            has_compat = True
        else:
            out_lines.append(ln)

    # Insert missing keys just before the closing '---'
    if not has_updated or not has_compat:
        # Find closing --- (last line) and insert above it
        # The frontmatter convention: leading '---', body lines, closing '---'
        # We expect the last entry to be '---'
        insert_at = len(out_lines) - 1
        if not has_compat:
            out_lines.insert(insert_at, "pandoc_compatible: true")
            insert_at = len(out_lines) - 1
        if not has_updated:
            out_lines.insert(insert_at, f"updated: {today}")

    return "\n".join(out_lines) + "\n"


def _split_body_and_fns(body_text: str) -> tuple[str, str]:
    """Find the first ``<sup>1</sup>`` line and split there.

    Anything before that line is body; from that line onward is the
    footnote-definition block. We anchor on ``<sup>1</sup>`` specifically
    (not just ``<sup>\\d+</sup>``) because the body may legitimately use
    inline ``<sup>`` for symbol superscripts elsewhere, though Cambridge
    Core exports rarely do.
    """
    m = re.search(r"^<sup>1</sup>\s", body_text, re.MULTILINE)
    if not m:
        return body_text, ""
    return body_text[: m.start()], body_text[m.start() :]


def _parse_fn_defs(fn_block: str) -> dict[int, str]:
    """Return {fn_number: definition_text} from a clippings-style FN block.

    Each definition starts on its own line with ``<sup>N</sup>``. The
    definition text is everything up to (but excluding) the next such
    line, with trailing whitespace trimmed. Multi-line definitions are
    therefore preserved verbatim, including their Google-Scholar tail.
    """
    defs: dict[int, str] = {}
    matches = list(_FN_DEF_LINE_RE.finditer(fn_block))
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start_of_text = m.start(2)
        end_of_def = matches[i + 1].start() if i + 1 < len(matches) else len(fn_block)
        text = fn_block[start_of_text:end_of_def].rstrip()
        defs[n] = text
    return defs


def _convert_body_markers(
    body: str, fn_numbers: list[int]
) -> tuple[str, list[int], list[int]]:
    """Replace inline FN markers in body using the n+1 sequence strategy.

    Returns (converted_body, missing_numbers, leftover_numbers).
    ``missing_numbers`` are FN numbers we never matched in the body;
    ``leftover_numbers`` is currently always empty (we don't search
    beyond the declared range), kept for forward compatibility.
    """
    out: list[str] = []
    pos = 0
    missing: list[int] = []
    for n in fn_numbers:
        pattern = re.compile(rf"(?<=[{_PRE_CHARS}]){n}(?!\d)")
        m = pattern.search(body, pos)
        if m is None:
            missing.append(n)
            continue
        out.append(body[pos : m.start()])
        out.append(f"[^{n}]")
        pos = m.end()
    out.append(body[pos:])
    return "".join(out), missing, []


def _format_pandoc_fns(fn_defs: dict[int, str]) -> str:
    """Render footnote definitions in Pandoc's ``[^N]: text`` form."""
    lines = []
    for n in sorted(fn_defs):
        # Collapse internal newlines to single spaces — Pandoc handles
        # multi-paragraph FN bodies via leading whitespace continuation,
        # but the clippings form is consistently single-paragraph and
        # already includes its Google-Scholar tail on the same line.
        text = re.sub(r"\s+", " ", fn_defs[n]).strip()
        lines.append(f"[^{n}]: {text}")
    return "\n".join(lines)


def convert(text: str) -> ConversionResult:
    """Convert a clippings-style Markdown string to Pandoc-style footnotes."""
    fm_block, rest = _split_frontmatter(text)
    body_text, fn_block = _split_body_and_fns(rest)
    fn_defs = _parse_fn_defs(fn_block)

    fn_numbers = sorted(fn_defs)
    new_body, missing, leftover = _convert_body_markers(body_text, fn_numbers)
    formatted_fns = _format_pandoc_fns(fn_defs)
    new_fm = _update_frontmatter(fm_block)

    parts = [new_fm, new_body.rstrip(), "\n\n", formatted_fns, "\n"]
    return ConversionResult(
        text="".join(parts),
        total_fn_defs=len(fn_defs),
        converted_in_body=len(fn_defs) - len(missing),
        missing_in_body=missing,
        extra_in_body=leftover,
    )


def convert_file(
    src: str | Path,
    out: str | Path | None = None,
    *,
    dry_run: bool = False,
) -> ConversionResult:
    """Convert ``src`` and (unless dry-run) write the result to ``out``.

    When ``out`` is ``None``, the sidecar ``<src-stem>.pandoc.md`` is
    written next to the input. ``dry_run=True`` performs the conversion
    in memory and returns the result without touching disk — used by the
    CLI's ``--dry-run`` flag to preview missing/extra markers.
    """
    src_path = Path(src)
    text = src_path.read_text(encoding="utf-8")
    result = convert(text)

    if dry_run:
        return result

    if out is None:
        out_path = src_path.with_suffix(".pandoc.md")
        if out_path == src_path:
            # ``foo.md`` -> ``foo.pandoc.md`` (with_suffix replaces only the
            # final suffix; force-append if the input was suffix-less).
            out_path = src_path.parent / f"{src_path.name}.pandoc.md"
    else:
        out_path = Path(out)

    out_path.write_text(result.text, encoding="utf-8")
    return result
