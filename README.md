# archilles-lector

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
lector extract input.pdf --out build/pages/   # PDF -> per-page TXT
lector reflow  build/pages/ --out book.md     # TXT dir -> Markdown
lector all     input.pdf --out book.md        # one-shot
```

## Layout

```
src/lector/
  cli.py                # argparse dispatcher
  pipeline.py           # end-to-end orchestration
  extract/
    pymupdf_backend.py  # primary text extraction
    ocr_backend.py      # stub, deferred
  reflow/
    core.py             # main reflow algorithm
    calibration.py      # line-length threshold detection
    footnotes.py        # marker substitution, audit, rescue
    regions.py          # frontmatter / main / entries / raw mode
    markdown.py         # MD rendering (Pandoc footnotes, headings)
    running_elements.py # header/footer detection (adapted from Archilles)
skills/pdf-text-reflow/  # in-repo copy of the Claude skill
tests/fixtures/          # golden files
```

## Related

- `archilles` — main project
- `archilles-dictator` — speech-to-text companion
- Skill: `pdf-text-reflow` (global at `~/.claude/skills/pdf-text-reflow/`,
  mirrored here)
