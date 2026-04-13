"""Reflow for ``prepared`` single-file TXT markup.

Unlike ``core.py`` (which reverses OCR layout damage from per-page files),
this module handles a single TXT file the user has prepared by hand. The
markup convention:

- ``---`` on its own line marks a page break. Does **not** break paragraphs;
  a paragraph may span the page boundary.
- ``--`` on its own line marks the start of the footnote region on the
  current page.
- ``[p. 211]`` / ``[p.212]`` at the start of a page body becomes ``[S. 211]``
  inline in the Markdown output.
- Footnote markers in the body are written as ``(1)``, ``(2)``, ``(*)`` etc.
  Footnote definitions in the footnote region start with the same token.
- Paragraph breaks inside a page body are blank lines.
- Footnote numbering resets per page. The renderer assigns a document-wide
  global counter so Pandoc footnote IDs are unique.

Output: Markdown with Pandoc-style footnotes (``[^1]`` in body,
``[^1]: text`` at the document end) and inline ``[S. NN]`` page markers.
"""

from __future__ import annotations

import re
from pathlib import Path

# Page break and footnote-separator lines
PAGE_BREAK_SPLIT = re.compile(r"\n---[ \t]*\n")
FN_SEP_SPLIT = re.compile(r"\n--[ \t]*\n")
# Page marker at start of body. Accepts all user-visible variants:
#   [p. 211]  [p.212]  [S. 223]  [S.224]  [222]
PAGE_MARKER_RE = re.compile(r"^\s*\[(?:p\.?\s*|S\.?\s*)?(\d+)\]")
# Footnote definition: line starting with (key) where key is * or 1-3 digits
FN_DEF_RE = re.compile(r"^\((\*|\d{1,3})\)\s*(.*)$")
# Combined body scanner: [S. NN] placed marker or (key) inline footnote marker
BODY_SCAN_RE = re.compile(r"\[S\.\s*(\d+)\]|\((\*|\d{1,3})\)")


def _parse_page(page_text: str) -> tuple[int | None, str, dict[str, str]]:
    """Split a single page block into (page_num, body_text, footnotes_by_key).

    The body text has its leading ``[p. NNN]`` replaced with ``[S. NNN]``.
    """
    parts = FN_SEP_SPLIT.split(page_text, maxsplit=1)
    body = parts[0]
    fn_block = parts[1] if len(parts) > 1 else ""

    # Case: block contains only footnote definitions without a leading `--`
    # separator (a continuation block where the user split the FN section of
    # one PDF page across two markdown blocks). Treat the whole thing as a
    # footnote block so its defs aren't lost.
    if not fn_block and body.strip():
        first_nonempty = next((ln for ln in body.split("\n") if ln.strip()), "")
        if FN_DEF_RE.match(first_nonempty):
            fn_block = body
            body = ""

    m = PAGE_MARKER_RE.match(body)
    page_num = int(m.group(1)) if m else None
    if m:
        body = body[: m.start()] + f"[S. {m.group(1)}]" + body[m.end() :]

    fns_raw: dict[str, list[str]] = {}
    order: list[str] = []
    current_key: str | None = None
    for line in fn_block.split("\n"):
        dm = FN_DEF_RE.match(line)
        if dm:
            current_key = dm.group(1)
            if current_key not in fns_raw:
                fns_raw[current_key] = []
                order.append(current_key)
            rest = dm.group(2).strip()
            if rest:
                fns_raw[current_key].append(rest)
        elif current_key is not None and line.strip():
            fns_raw[current_key].append(line.strip())

    fns = {k: " ".join(fns_raw[k]).strip() for k in order}
    return page_num, body, fns


def _split_paragraphs(lines: list[str]) -> list[str]:
    """Group lines into paragraphs. Blank line = paragraph separator.

    Within a paragraph, lines are joined with a single space.
    """
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in lines:
        if line.strip() == "":
            if buf:
                paragraphs.append(" ".join(s.strip() for s in buf if s.strip()))
                buf = []
        else:
            buf.append(line)
    if buf:
        paragraphs.append(" ".join(s.strip() for s in buf if s.strip()))
    return paragraphs


def convert(text: str) -> tuple[str, dict[int, list[str]]]:
    """Convert prepared-markup text to Markdown.

    Returns ``(markdown, audit)`` where ``audit`` maps page number to the
    list of footnote keys that were defined but never referenced in the body.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")

    page_blocks = PAGE_BREAK_SPLIT.split(text)
    page_blocks = [p for p in page_blocks if p.strip()]

    pages: list[dict] = []
    for raw in page_blocks:
        num, body, fns = _parse_page(raw)
        # Merge a "FN continuation" block (no body, no page num) into the
        # previous page — the user split one PDF page across two blocks.
        if num is None and not body.strip() and fns and pages:
            pages[-1]["fns"].update(fns)
            continue
        pages.append({"num": num, "body": body, "fns": fns})

    num_to_idx: dict[int, int] = {}
    for i, p in enumerate(pages):
        if p["num"] is not None and p["num"] not in num_to_idx:
            num_to_idx[p["num"]] = i

    all_lines: list[str] = []
    for p in pages:
        all_lines.extend(p["body"].split("\n"))

    paragraphs = _split_paragraphs(all_lines)

    global_defs: list[tuple[int, str]] = []
    local_to_global: dict[tuple[int, str], int] = {}
    consumed: set[tuple[int, str]] = set()
    current_page_idx: int | None = None

    rewritten: list[str] = []
    for para in paragraphs:
        out: list[str] = []
        pos = 0
        for m in BODY_SCAN_RE.finditer(para):
            out.append(para[pos : m.start()])
            if m.group(1) is not None:
                page_num = int(m.group(1))
                current_page_idx = num_to_idx.get(page_num, current_page_idx)
                out.append(f"[S. {page_num}]")
            else:
                local_key = m.group(2)
                assigned = False
                if current_page_idx is not None:
                    fn_text = pages[current_page_idx]["fns"].get(local_key)
                    if fn_text is not None:
                        key = (current_page_idx, local_key)
                        if key not in local_to_global:
                            global_num = len(global_defs) + 1
                            local_to_global[key] = global_num
                            global_defs.append((global_num, fn_text))
                        out.append(f"[^{local_to_global[key]}]")
                        consumed.add(key)
                        assigned = True
                if not assigned:
                    out.append(m.group(0))
            pos = m.end()
        out.append(para[pos:])
        rewritten.append("".join(out))

    audit: dict[int, list[str]] = {}
    for idx, p in enumerate(pages):
        unclaimed = [k for k in p["fns"] if (idx, k) not in consumed]
        if unclaimed and p["num"] is not None:
            audit[p["num"]] = unclaimed
            # Append unclaimed defs to the end of the document so nothing is lost.
            for k in unclaimed:
                global_num = len(global_defs) + 1
                local_to_global[(idx, k)] = global_num
                global_defs.append((global_num, p["fns"][k]))
                # Hang a reference onto the last paragraph that touched this page.
                target_para = None
                for pi in range(len(rewritten) - 1, -1, -1):
                    if f"[S. {p['num']}]" in rewritten[pi]:
                        target_para = pi
                        break
                if target_para is None:
                    target_para = len(rewritten) - 1
                rewritten[target_para] = rewritten[target_para].rstrip() + f" [^{global_num}]"

    md_body = "\n\n".join(rewritten).rstrip()
    if global_defs:
        md_body += "\n\n" + "\n\n".join(f"[^{n}]: {t}" for n, t in global_defs)
    return md_body + "\n", audit


def convert_file(src: str | Path, out: str | Path) -> dict[int, list[str]]:
    src = Path(src)
    out = Path(out)
    text = src.read_text(encoding="utf-8", errors="replace")
    md, audit = convert(text)
    out.write_text(md, encoding="utf-8")
    return audit
