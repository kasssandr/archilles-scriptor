# Producing candidate outputs

Outputs land in eval/outputs/<volume>/<tool>.md (gitignored). One venv per
foreign tool (they conflict); versions are recorded IN the output filename
when a rerun matters, e.g. xberg-0.1.0.md. Foreign outputs are evaluated
with the plain adapter automatically (anything not *.review.md/*.prepared.md).

## scriptor (ours — evaluate the REVIEW copy)
scriptor reflow eval/golden-local/<vol>/pages/ --out /tmp/<vol>.md
cp /tmp/<vol>.review.md eval/outputs/<vol>/scriptor.review.md

## pymupdf4llm (raw baseline, no apparatus logic)
python -c "import pymupdf4llm, pathlib; \
  pathlib.Path('eval/outputs/<vol>/pymupdf4llm.md').write_text( \
  pymupdf4llm.to_markdown('corpora/<vol>.pdf'), encoding='utf-8')"

## xberg (hand-checked 2026-07-17: CPU-fast, apparatus-destroying — that is
## the point of measuring it)
pip install xberg   # own venv
xberg extract corpora/<vol>.pdf -o eval/outputs/<vol>/xberg.md
# exact CLI flags: check `xberg --help` at run time; the tool is young and
# its interface moved between kreuzberg 4.x and xberg 0.1.

## marker
pip install marker-pdf   # own venv, GPU optional
marker_single corpora/<vol>.pdf /tmp/marker-out && \
  cp /tmp/marker-out/<vol>/<vol>.md eval/outputs/<vol>/marker.md

## docling
pip install docling      # own venv
docling corpora/<vol>.pdf --to md --output eval/outputs/<vol>/ && \
  mv eval/outputs/<vol>/<vol>.md eval/outputs/<vol>/docling.md

## assemble the draft (LOCAL ONLY — benchmark embargo, do not commit/quote)
scriptor eval suite --golden-dir eval/golden --golden-dir eval/golden-local \
    --outputs-dir eval/outputs --out eval/BENCHMARK-draft.md
