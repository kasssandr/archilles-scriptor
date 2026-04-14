# archilles-scriptor

PDF → Markdown converter for scholarly prose. Subproject of the Archilles family.

Reverses layout damage from PDF/OCR extraction (hard line wraps, hyphenation,
detached footnotes, running headers) and produces clean, footnote-anchored
Markdown suitable for further editing and translation.

## Status

Early work. Targets well-typeset text PDFs first; scanned PDFs are out of scope
until OCR backend is wired up.

## Pipeline

```
PDF → extract (pymupdf4llm) → per-page TXT → reflow → Markdown
```

## CLI

```bash
scriptor extract input.pdf --out build/pages/   # PDF -> per-page TXT
scriptor reflow  build/pages/ --out book.md     # TXT dir -> Markdown
scriptor all     input.pdf --out book.md        # one-shot
```

## Layout

```
src/scriptor/
  cli.py                # argparse dispatcher
  pipeline.py           # end-to-end orchestration
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

- `archilles` — main project
- `archilles-dictator` — speech-to-text companion
- Skill: `pdf-text-reflow` (global at `~/.claude/skills/pdf-text-reflow/`,
  mirrored here)
