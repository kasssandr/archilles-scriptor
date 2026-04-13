---
name: pdf-text-reflow
description: Use when the user has a directory of OCR/PDF-extracted page-per-file text from a printed book or paper and wants to reconstruct continuous prose — joins hyphenated words, rebuilds paragraphs, attaches footnotes to the end of their containing paragraph (indented), preserves page numbers as inline `[S. NN]` markers and footnote markers as `[NN]`.
---

# PDF/OCR Text Reflow

Reverse the layout damage that PDF/OCR extraction does to printed prose:
hard line wraps, hyphenated words split across lines, footnotes detached
from their paragraphs, page numbers and column-major scan order. Produce a
single continuous TXT file that retains page numbers and footnote anchors
without their layout artifacts.

The reference implementation `reflow.py` ships with the skill and is the
starting point for any new project. Copy it next to the OCR files, adapt
its `HEADING_TRIGGERS` if needed, then run it.

## When to use

Trigger this skill whenever the user has:

- a directory full of `00000001.txt … 00000NNN.txt` files (one per scanned page)
- a single huge OCR text dump that still preserves page boundaries
- any prose source where line wraps, hyphenation and footnote position
  obscure the original paragraph structure

Don't use it for code, tables, sheet music, math, or columnar reference
material — the algorithm assumes flowing prose.

## Output conventions

Two output formats are supported: **TXT** (default) and **Markdown**.
The format is auto-detected from the output file extension (`.md` → md),
or can be forced with `--format md|txt`.

### TXT mode

| Marker | Meaning |
|---|---|
| `[S. 34]` | Inline page-start marker (book page number) |
| `[NN]` | Footnote anchor in the body |
| `    [NN] text…` | Footnote text, 4-space indent, listed at the end of its paragraph in numerical order |
| blank line | Paragraph separator |
| `[Inhaltsverzeichnis ausgelassen]` | Skipped TOC |

### Markdown mode

| Marker | Meaning |
|---|---|
| `[S. 34]` | Inline page-start marker (kept as plain text — no native MD equivalent) |
| `[^N]` | Pandoc-style footnote reference with **global** numbering |
| `[^N]: text` | Footnote definition, emitted once at the **end of the document** |
| `# Titel` / `## Titel` / `### Titel` | Numbered headings (e.g. `3.4. Probleme…` → `## 3.4. Probleme…`); heading level = depth of the number (dots + 1) |
| blank line | Paragraph separator |

**Why global footnote numbers in MD**: Hechberger (and many German
academic books) reset footnote numbering per chapter, but Pandoc/CommonMark
footnote IDs must be unique document-wide. The MD renderer therefore
assigns a running global counter and writes all definitions in order at
the end of the document.

**Why no indented footnotes in MD**: a 4-space indent at the start of
a line is a code block in Markdown. Footnote definitions must therefore
live outside the paragraph, which is the standard Pandoc placement anyway.

When a paragraph crosses a page boundary, the `[S. NN]` marker is placed
inline at the page boundary; if the page break falls inside a hyphenated
word, the marker shifts to the next whitespace position so it never lands
mid-word.

## Algorithm

The script makes a single pass over the page files in name order. The
hard parts:

### 1. Page parsing (`parse_page`)

Per file:
1. Strip trailing blank lines.
2. If the last line is a bare integer (1–4 digits), it's the printed page number.
3. The footnote block is everything from the first line matching `^NN)` to the end.
4. Body = everything before the footnote block.
5. Translate Unicode superscript digits (`²³⁴⁵⁶⁷⁸⁹⁰¹`) to ASCII — OCR
   sometimes preserves footnote anchors as superscripts.
6. Substitute footnote markers in the body via two-pass matching
   (see "Footnote markers" below).

### 2. Region/mode assignment (`assign_modes`)

Books have heterogeneous regions that need different treatment. Modes:

| Mode | Treatment |
|---|---|
| `frontmatter` | Pages before `book p.1`. Preserve original lines. |
| `toc` | Inhaltsverzeichnis. Skipped (replaced with marker). |
| `main` | Body of the book. Full reflow algorithm. |
| `entries-versal` | Bibliography with VERSAL surnames. Each line starting `^[A-ZÄÖÜ]{2,}` begins a new entry. |
| `raw` | Lists where OCR column order is broken (Abkürzungsverzeichnis, Quellen, indices). Preserve original lines. |

Mode is detected by scanning the first 10 non-empty body lines per page
for heading patterns in `HEADING_TRIGGERS`. **Adapt this list per book.**
Default triggers fit Hechberger 1996 / Böhlau house style:

```python
HEADING_TRIGGERS = [
    (re.compile(r"^INHALTSVERZEICHNIS\s*$"), "toc"),
    (re.compile(r"^\d+\.\s+Literatur\s*$"), "entries-versal"),
    (re.compile(r"^\d+\.\s+(Abkürzungsverzeichnis|Quellen|Personenregister|Sachregister|Ortsregister)\s*$"), "raw"),
]
```

The first 10-line window matters: column-major OCR routinely puts
abbreviations from the first column ahead of the section heading.

### 3. Calibration (`calibrate_threshold`)

The hardest sub-problem is paragraph-end detection. The OCR contains no
explicit paragraph markers — the only signal is line length. A "full"
fließtext line is close to the typeset measure (~70 characters in Böhlau
print); a "short" line is one that didn't fill the measure, which usually
means it's the last line of a paragraph.

Procedure:
1. Build a histogram of body-line lengths from `main`-mode pages only.
2. Find the mode (the most common length — peak of the distribution).
3. Walk left from the mode until count drops below 25 % of peak count.
4. That position is the **left edge** of the filled-line peak.
5. Threshold = left_edge − 1. Any body line with `len ≤ threshold` ending
   in sentence-final punctuation (`.!?»"'`) is treated as a paragraph end.

For Hechberger this gives threshold = 64 (peak at 70, left edge at 65).
The user verified this matches a manual measurement in LibreOffice.

If the histogram has a long tail of very short lines (TOC, headings,
indices), this approach is robust because it ignores them — they don't
contribute to the peak.

### 4. Body reconstruction (`reconstruct_body`)

For `main` pages, walk lines and emit a paragraph stream:

- **Hyphen handling**: a line ending `letter-` joins to the next line
  without a space, unless `is_hard_hyphen()` says the next line begins
  with a German connector (`und/oder/bis/sowie/wie/als/zur?/zum?/noch/aber`).
  Connector → keep the literal hyphen and add a space (so
  `Einzel- und Gesamtanalyse` survives intact instead of becoming
  `Einzelund Gesamtanalyse`). This is the most error-prone heuristic and
  may need extending per book.

- **Page marker placement**: when a new page begins, queue the
  `[S. NN]` marker; emit it after the current word completes (i.e., never
  mid-hyphenated-word).

- **Paragraph end**: a line that ends in sentence-final punctuation AND
  whose visible length is ≤ threshold ends the current paragraph. The
  last line of a page is **not** excluded — pages do legitimately end
  paragraphs at the bottom margin.

- **Footnote bookkeeping**: when a `[NN]` marker is seen on a line whose
  page defined footnote NN, the footnote text is recorded against the
  current paragraph and rendered indented at the paragraph end.

### 5. Footnote markers (`substitute_markers`)

Done at parse time, per page, in two passes:

1. **Attached** (high confidence): for each footnote number `NN` defined
   on the page, find the first occurrence of `\S NN` (immediately after
   non-whitespace) and replace with ` [NN]`.
2. **Whitespace-separated** (fallback): for any number not yet matched,
   look for `\s NN` (preceded by whitespace) and replace with `[NN]`.

Each footnote number is consumed at most once. Numbers that don't appear
as a footnote definition on the same page are left as plain digits — this
prevents years (`1147`) and counts (`5 Argumente`) from being mis-marked.

Coverage on Hechberger: 1387 of 1557 footnote definitions (89 %).
The 11 % shortfall is mostly:
- Front matter / TOC (no proper Arabic page numbers)
- Footnote definition on a different page than its anchor (column-scan
  artifacts in the Böhlau index region)
- Index/bibliography pages, where there are no real footnotes
- **OCR errors on the superscript marker**: the footnote def exists and
  is parsed, but the superscript digit in the body was lost or mis-read
  as a different digit. These are rescued by the audit mechanism below
  so they don't disappear silently.

### Audit mechanism for unanchored footnotes

At the end of each page, any footnote defined on that page whose marker
was never found in the body is appended to the last paragraph that
touched the page (as a hanging reference). This prevents silent data loss.

`render_book` also returns an `audit` dict keyed by book page number
listing the rescued footnote numbers. `main()` writes this to a sidecar
file `<output>.audit.txt` so the user can locate OCR marker errors:

```
S. 1: FN 1, 5
S. 2: FN 7, 8
S. 7: FN 5, 6
…
```

Hechberger run: 164 unanchored FNs on 113 pages. Most are real OCR
errors at the superscript position — the audit file is the starting
point for manual cleanup in the source TXTs.

### 6. Region rendering

`render_book` groups consecutive pages by mode and dispatches:

- `main` → `render_main` → paragraph stream + indented footnotes
- `frontmatter`, `raw` → `render_frontmatter` (preserve original lines per page)
- `toc` → single placeholder line
- `entries-versal` → `render_entries(VERSAL_RE)` (one entry per VERSAL block)

Output blocks are joined with blank lines.

## Usage

```bash
# from inside the directory of OCR text files
py reflow.py . output.txt          # TXT mode (auto-detected)
py reflow.py . output.md           # Markdown mode (auto-detected)
py reflow.py . output.foo --format md   # explicit override
```

Console output reports mode distribution and the calibrated threshold:

```
Modus-Verteilung: {'frontmatter': 8, 'toc': 3, 'main': 355, 'raw': 31, 'entries-versal': 91}
Kalibrierung (nur main): Schwellwert ≤ 65 Zeichen
```

If those numbers look wrong (e.g., `main` is too small, threshold is
absurdly low), debug **before** spending time inspecting output:

- Wrong mode counts → `HEADING_TRIGGERS` doesn't match the book's
  section names. Inspect the first 10 lines of the heading pages.
- Threshold near 0 or absurdly low → the histogram peak is being missed.
  Plot it (small ad-hoc script) and check whether the `peak_fraction`
  parameter in `calibrate_threshold` needs tuning.

## Adaptation checklist for a new book

When invoked for a new project, walk through this list before running:

1. **Inspect three sample pages** — early body, mid-body with footnotes,
   bibliography. Confirm:
   - Page numbers are bare integers on their own line (else: extend `PAGENUM_RE`)
   - Footnotes start with `NN)` (else: extend `FOOTNOTE_RE`)
   - Marker style: ASCII digits or Unicode superscripts (already handled)
2. **Check the Inhaltsverzeichnis** for the exact wording of the
   bibliography / index section headings. Update `HEADING_TRIGGERS`.
3. **Run once**, look at the mode distribution and threshold. Sanity check.
4. **Spot-check the output** at three places:
   - First main paragraph (page 1 area)
   - A paragraph spanning a page break with footnotes on both sides
   - The bibliography (verify entries are split, hyphenated words intact)
5. **Iterate on `KEEP_HYPHEN_BEFORE`** if you spot Kompositum-Bindestrich
   damage in the output.

## Known limitations

- **No column detection.** If OCR scanned columns left-to-right by line
  rather than column-by-column, abbreviation lists and indices come out
  scrambled. The `raw` mode preserves them as-is — manual cleanup needed.
- **Hard hyphen heuristic is shallow.** `KEEP_HYPHEN_BEFORE` only
  recognizes a small set of German connectors; e.g., `Bismarck- und
  Wilhelminismus-Forschung` → split at first `-`, second one would join.
  Extend the regex per book.
- **Section heading recovery is regex-based.** Lines matching
  `^\d+(\.\d+){0,3}\.\s+[A-ZÄÖÜ]` within `HEADING_MAX_LEN` characters are
  promoted to their own block. In MD mode they become `#`-headings with
  level = number of dots + 1. False positives are possible in index
  regions ("2. Clm 12631…") but main-body numbered chapters and
  subsections are reliably caught.
- **TOC and front matter are not parsed structurally.** TOC is dropped,
  front matter is preserved verbatim.
- **Cross-page footnote references** (marker on page N, definition on
  page N+1) are missed. Rare in well-typeset books.
- **LLM fallback for ambiguous paragraph breaks** is documented in the
  user's design but not implemented yet — would address the gap between
  the calibrated threshold and the true peak left edge.

## Where the script lives

The reference implementation is `reflow.py` in this skill directory.
Copy it into the OCR directory rather than importing it — it's small,
self-contained, and per-book customization is expected.
