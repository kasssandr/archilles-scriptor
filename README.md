# archilles-scriptor

PDF → Markdown converter for scholarly prose. Subproject of the Archilles family.

Reverses layout damage from PDF/OCR extraction (hard line wraps, hyphenation,
detached footnotes, running headers) and produces clean,
footnote-anchored Markdown suitable for further editing and translation.

## Status

Early work. Targets well-typeset text PDFs first; scanned PDFs are out of scope
until the OCR backend is wired up. Two ingestion paths besides PDF are
already supported: hand-prepared TXT files and Markdown clippings from
journal portals such as Cambridge Core / JSTOR / Traditio.

## Pipeline

```
PDF → extract (pymupdf4llm) → per-page TXT → reflow → Markdown
                                                      ▲
hand-prepared TXT ──────────────────────────────────── │   (prepared)
clippings (Cambridge Core / JSTOR style) .md ───────── ┘   (clippings)
```

Each input form has its own subcommand; they all converge on Pandoc-style
footnotes (`[^N]` body markers + `[^N]: text` definitions) and inline
`[S. NN]` page markers where applicable.

## CLI

```bash
# 1) Text PDF → per-page TXT (pymupdf4llm)
scriptor extract input.pdf --out build/pages/

# 2) Per-page TXT directory → reflowed Markdown
scriptor reflow build/pages/ --out book.md
scriptor reflow build/pages/ --out book.md --format md      # explicit format
scriptor reflow build/pages/ --out book.txt --format txt    # plain-text reflow

# 3) Full pipeline in one shot
scriptor all input.pdf --out book.md
scriptor all input.pdf --out book.md --pages-dir build/pages/

# 4) Hand-prepared TXT (--- / -- separators, (N) markers) → Markdown
scriptor prepared prepared_input.txt --out book.md

# 5) Cambridge-Core / JSTOR / Traditio Markdown clipping → Pandoc sidecar
scriptor clippings input.md                                 # writes input.pandoc.md
scriptor clippings input.md --out output.md
scriptor clippings input.md --dry-run                       # preview without writing
```

## Input formats

### `prepared` — hand-curated single-file TXT

For OCR text the user has cleaned up by hand. Convention:

| Markup | Meaning |
|---|---|
| `---` (own line) | Page break — does **not** break paragraphs; a paragraph may span pages |
| `--` (own line) | Start of the footnote region on the current page |
| `[p. 211]`, `[p.212]`, `[S. 223]`, `[S.224]`, `[222]` | Page marker at the start of a page body — rendered inline as `[S. 211]` in the Markdown |
| `(1)`, `(2)`, `(*)` … | Footnote markers in the body and footnote definitions in the FN region |
| Blank line | Paragraph break |

Footnote markers are local per page; the renderer assigns a
document-wide global counter so Pandoc footnote IDs stay unique. If a
footnote definition exists without a body marker (typical OCR artifact:
`?`, `*`, `°`, `'`, `"` mistaken for a superscript digit), it is
attached to the last paragraph of its page as a hanging reference and
listed in a sidecar audit file.

### `clippings` — Cambridge-Core / JSTOR / Traditio Markdown export

For Markdown clippings produced by web clippers from journal portals,
where footnote markers appear as bare digits attached to a word
(`religion.1`) and footnote definitions appear at the document end as
`<sup>N</sup> Text … [Google Scholar](URL)`.

Conversion rewrites both into Pandoc footnote syntax. The trick is that
many digits in scholarly prose are *not* footnote markers — years
(`1798`), scripture references (`Gen. 16:1-6`, `Deut. 21:10-13`),
parenthetical numbers (`(d. ca. 220)`), edition references
(`Stromateis 1.5.28-9.45`). Two safeguards rule those out:

- A **conservative pre-character class**: a digit qualifies as a
  footnote marker only when preceded by a Latin letter or a sentence-ending
  punctuation mark (`. , ; : ! ? ) ] " ' »`). Hyphens, opening brackets
  and digits are explicitly excluded — that rules out range constructs
  like `1-6` and parenthetical numbers like `(220)`.
- An **n+1 sequence constraint**: footnote numbers are resolved in
  ascending order. After matching `[^n]` at some position, the search
  for `[^n+1]` resumes only past that point. A stray digit that appears
  between two real markers can therefore never be substituted, and a
  missing real marker is simply reported in the audit instead of
  poisoning later substitutions.

Output is a sidecar file (`<input-stem>.pandoc.md`) so the original
clipping stays intact. The frontmatter is preserved and extended with
`updated:` (set to today) and `pandoc_compatible: true`. Google Scholar
links inside footnote definitions are kept verbatim — they survive
Pandoc round-trips and are useful when the converted document is later
machine-translated, since translators tend to mangle bibliographic
references but typically leave URL-bearing markdown links alone.

`--dry-run` performs the conversion in memory and reports
`converted/total` plus any missing footnote numbers, without writing
the sidecar. Use it before the first run on any new source — missing
markers usually indicate OCR artifacts in the clipping that the user
needs to repair before the conversion is complete.

## Layout

```
src/scriptor/
  cli.py                # argparse dispatcher (extract / reflow / all / prepared / clippings)
  pipeline.py           # end-to-end orchestration for the PDF path
  clippings.py          # journal-clipping single-file path
  extract/
    pymupdf_backend.py  # primary text extraction
    ocr_backend.py      # stub, deferred
  reflow/
    core.py             # main reflow algorithm (monolithic; split planned)
    prepared.py         # prepared-markup single-file path
    running_elements.py # header/footer detection (adapted from Archilles)
skills/pdf-text-reflow/  # in-repo copy of the Claude skill
tests/fixtures/          # golden files
```

> **Planned:** `core.py` to be split into `calibration.py` (line-length
> threshold), `footnotes.py` (marker substitution, audit, rescue),
> `regions.py` (frontmatter / main / entries / raw mode) and `markdown.py`
> (MD rendering). Not yet implemented.

## Related

- `archilles` — main project (RAG over Calibre libraries with
  page-level citations, MCP integration)
- `archilles-dictator` — speech-to-text companion
- Skill: `pdf-text-reflow` (global at `~/.claude/skills/pdf-text-reflow/`,
  mirrored here under `skills/`)
