# archilles-scriptor

Turns scholarly PDFs into Markdown whose footnotes are still attached to the
sentence they belong to.

## The problem

In the humanities the argument sits in the body and the evidence sits in the
footnotes. Strip the apparatus and a page of Byzantine history becomes an
anecdote. A citation you cannot follow is worth nothing.

Every PDF-to-text tool handles the prose acceptably and the apparatus badly,
for a typographic reason. Footnote markers are superscript digits set at maybe
five points. OCR reads a superscript 6 as `&`, a 1 as `l`, a 4 as `A`. The
footnote text at the bottom of the page usually survives, because it is set in
running size. The marker that anchored it to a sentence does not. What comes
out is a body with no anchors and a heap of orphaned notes.

Nothing downstream repairs this. Not a RAG chunker, not a translation model,
not an LLM reading the file. The information was destroyed before any of them
saw it. And a footnote silently reattached to the wrong sentence is worse than
a missing one: you find out years later, when you follow the citation.

## What scriptor does

It rebuilds the paragraphs that the PDF's hard line wraps broke apart, joins
hyphenated words, drops running headers, and keeps page boundaries as inline
`[p. NN]` markers. The marker carries the page label as *printed*, so a
roman-paginated preface stays citable as `[p. xiv]` rather than being renumbered
or dropped. Page-local footnotes become document-wide Pandoc footnotes.

Where a marker was lost, it does not guess silently. Take this scanned page:

```
Firstly5 then the work& and later7 the conclusion follows here.
5) Fifth note.
6) Sixth note without a marker in the body.
7) Seventh note.
```

Note 6 has a definition and no marker. The `&` after "work" is where the
superscript 6 used to be. Scriptor knows a marker is missing, because 6 sits
between two markers it did recognise, and it knows `&` is a glyph a superscript
6 is commonly misread as. So it writes a clean file:

```markdown
[p. 1] Firstly [^1] then the work& and later [^2] the conclusion follows here. [^3]

[^1]: Fifth note.

[^2]: Seventh note.

[^3]: Sixth note without a marker in the body.
```

and the review one, identical except for the flag:

```markdown
[p. 1] Firstly [^1] then the work&[?FN:6|&] and later [^2] the conclusion ...
```

The clean file never carries a flag, so it stays valid Pandoc and stays
translatable. Note 6 survives there as an unreferenced definition rather than
being dropped or attached to a guess. The doubt lives in the review file, in an
audit sidecar, and in a decision file you can answer with one keystroke (see
below). Correcting one flagged glyph is a two-second job. Finding it yourself in
a 400-page volume is not.

## Status

Working: three text ingestion paths, the reflow, Pandoc footnotes, the
confidence layer, within-document glyph learning that carries across a
corrected corpus, the decision loop, a translation profile, and a DOCX footnote
binder. 224 tests, about 3,900 lines of Python. It has been run against real
volumes (Baynes, *Byzantium*; Snell, *Die Entdeckung des Geistes*), which is
where most of the edge cases came from.

Not working: scanned PDFs. `extract/ocr_backend.py` raises
`NotImplementedError`. Text PDFs and the text-based paths below are what exist
today.

## Install

```bash
git clone https://github.com/kasssandr/archilles-scriptor
cd archilles-scriptor
pip install -e .
```

Python 3.11 or newer.

## Quickstart

```bash
scriptor all book.pdf --out book.md
```

## What a run writes

| File | Contents |
|---|---|
| `book.md` | Clean Pandoc Markdown, no flags. This is what you feed a translator or a vector store. |
| `book.review.md` | The same text plus inline uncertainty flags. This is the file you read. |
| `book.md.audit.txt` | One line per uncertain footnote: page, confidence class, candidate glyphs with scores and the reason each was scored that way. Plus a run summary, so you know before you start whether the volume needs two corrections or two hundred. |
| `book.md.decisions.txt` | The still-open choices, one line per candidate, each with an empty box. This is the file you edit. |

## Input formats

Each input has its own subcommand. They all converge on the same output.

```bash
scriptor extract input.pdf --out build/pages/   # text PDF -> per-page JSON page model
scriptor extract input.pdf --out build/pages/ --emit-txt   # …and a readable text copy
scriptor reflow build/pages/ --out book.md      # page model (or legacy TXT) -> Markdown
scriptor reflow build/pages/ --out book.txt --format txt
scriptor reflow build/pages/ --out book.md --decisions book.md.decisions.txt

scriptor prepared cleaned.txt --out book.md     # hand-corrected single TXT
scriptor clippings article.md                   # Cambridge Core / JSTOR export
scriptor pages-zip book.zip --out book.md       # Internet Archive page ZIP
scriptor learn *.decisions.txt --out corpus.json # corrected corpus -> OCR profile
```

`prepared` reads a convention: `---` on its own line is a page break that does
not break paragraphs, `--` opens the footnote region, `(1)` is a marker, and a
page marker may be written `[p. 211]`, `[S. 223]` or bare `[222]`.

`clippings` handles Markdown exports from journal portals, where markers appear
as bare digits glued to a word (`religion.1`) and definitions collect at the
end as `<sup>N</sup> Text`. The hard part is that most digits in scholarly prose
are not footnote markers: years, scripture references (`Deut. 21:10-13`),
edition references (`Stromateis 1.5.28-9.45`). Two rules rule them out. A digit
qualifies only when preceded by a letter or sentence-ending punctuation, never
by a hyphen, an opening bracket, or another digit. And numbers resolve in
ascending order, so the search for marker *n+1* resumes past the position of
*n*. A stray digit between two real markers can never be substituted. Output
goes to a sidecar; the original clipping stays untouched.

`pages-zip` unpacks Internet Archive `_djvu.txt` archives, sorts pages
naturally (`page_9` before `page_10`), skips covers and plates, and recovers
from the encodings that old OCR text tends to be in.

## The confidence layer

Borrowed from error propagation in physics: name the uncertainty at its source
and carry it through the calculation, rather than discovering at the end that
the answer does not add up.

An unclaimed footnote is classified by what the candidate search finds in the
gap:

| Class | Meaning | In the review file |
|---|---|---|
| certain | Marker present, sequence intact. | Set cleanly, no flag. |
| suggested | Exactly one plausible candidate. | `[?FN:6\|&]` |
| guessed | Several candidates, or weak evidence. | One `[??FN:6\|&:0.7]` per candidate, each at its own position |
| orphan | No candidate at all. | `[?FN:6]` at the end of the paragraph |

The candidate search is deliberately narrow. It only fires on an *interior
gap*, one bounded by a confidently placed marker both below and above it in
number order. It never considers a glyph wedged mid-word. It scores by an OCR
confusion table (`OCR_CONFUSION` in `reflow/confidence.py`, kept as data, not
code) plus position: is the glyph attached to a word end, does punctuation
follow. Every score and every rejection lands in the audit with its reason.

Edge gaps stay unflagged, and their text is preserved as a hanging reference at
the end of the paragraph. Under-flagging is the cheaper failure. A reader who
learns to ignore flags has lost the whole benefit.

### What the book teaches the run

A volume was scanned once, in one typeface, by one engine. Whatever it made of a
superscript 2, it made of every superscript 2. So before scoring anything,
scriptor counts which glyphs actually stand in this document's own sequence gaps,
and weights them by what it finds:

```
Glyph evidence for footnote 2: 'z' 6x (86%), 'Z' 1x (14%)
```

A glyph the volume repeats says so in the decision file:

```
[ ] p. 6  fn 2  cand 1  'z'  conf 0.9  seen 6x  ctx: …bore the mintZ or the mintz mark and the die [3]…
[ ] p. 6  fn 2  cand 2  'Z'  conf 0.7  ctx: …bore the mintZ or the mintz mark and the die [3]…
```

The effect is not subtle. A gap holding both `z` and `Z` is a coin toss to the
flat table — two rivals, equal scores, and the review file asks you to choose.
With the book's own statistics the choice is already made: one flag instead of
two, and `z` ranked first rather than whichever happened to come earlier in the
line. Since the decision file's `cand 1` means "the best candidate", getting that
order right matters as much as getting the class right.

Two guardrails hold this in place. Evidence may **reweight and rank** the
candidates the structural rules found; it may never add one, drop one, or open a
gap. And a score lead only settles a choice when statistics back it — without
them a lead means merely "better placed", which is not enough.

None of this costs reproducibility. The statistics are a pure function of the
pages: nothing accumulates between runs behind your back, so the same volume
always yields the same decision file.

### Learning across volumes

One book has one book's worth of evidence. A gap you see for the first time, in a
volume too thin to have a pattern of its own, gets no help from the paragraph
around it. But you may have corrected the same typeface before, and those
corrections are sitting in the decision files you already answered. `scriptor
learn` turns them into a profile:

```bash
scriptor learn *.md.decisions.txt --out corpus.json
scriptor reflow pages/ --out book.md --ocr-profile corpus.json
```

The profile carries a different kind of evidence from the within-document count,
and the code keeps the two apart. A document count says "this glyph once stood in
a gap" — a guess the confusion table proposed. A profile entry says "a human
confirmed this glyph *is* that digit". So a profile enters scoring as a handful of
pseudo-observations: enough to rank a book that has nothing of its own to go on,
never enough to outvote a book that does. The volume's own typography always wins,
because it is the same scan under the same lens. And it stays an explicit file for
the same reason the decision loop does — a table that grew as a side effect of
past runs would make today's pages score differently tomorrow.

## Correcting what the machine would not decide

Scriptor flags rather than guesses, which leaves you with a worklist. You do not
edit the Markdown to resolve it. You mark a decision and run the reflow again:

```bash
scriptor reflow build/pages/ --out book.md                    # 1. flags the doubts
$EDITOR book.md.decisions.txt                                 # 2. you put an x in a box
scriptor reflow build/pages/ --out book.md \
    --decisions book.md.decisions.txt                         # 3. places the markers
```

The decision file is generated for you:

```
[ ] p. 1  fn 6  cand 1  '&'  conf 0.8  ctx: …then the work& and later [7] the conclusion…
```

Put an `x` in the box and footnote 6 is anchored where that `&` sits — the glyph
is replaced by the marker, because the glyph *is* the marker, misread. Leave the
box empty and the footnote stays an unreferenced definition at the end of its
paragraph. Nothing is lost either way. Marking two candidates for one footnote is
refused rather than resolved by guessing. The file is regenerated on every run and
shrinks as you work.

This works because the pipeline is deterministic: no model sits in the loop, so
the same pages and the same code always produce the same candidates. Replaying the
run with your decisions reproduces every certain choice untouched and applies the
uncertain ones you made. A round trip through the rendered Markdown would be worse
as well as harder — the master records only the document-wide id `[^3]`, never the
page-local footnote it came from, so it cannot be read back into the model at all.
Determinism replaces the round trip.

## Preparing text for translation

```bash
scriptor translate-prep book.md --out book.translate.md
```

Machine translators cheerfully render *Römische Geschichte* as *Roman History*,
which turns a bibliographic reference into a dead end. Two layers of defense.
Scriptor tags what it can prove is bibliographic (URLs, quoted work titles in
footnote definitions) with `<dnt>…</dnt>`, which is hard, auditable protection.
The briefing sidecar it writes alongside tells the translating model to leave
the rest of the apparatus alone, which is soft protection for the cases no rule
can catch, such as a title sitting bare in the middle of a footnote sentence.
Open confidence flags are stripped on the way out, so the result is always
translatable Pandoc.

## Binding footnotes in DOCX

```bash
scriptor bind-footnotes in.docx --out out.docx
```

For documents whose footnotes were flattened into loose `N.)` paragraphs.
Scriptor uses the surviving superscript run as its signal, matches definitions
to references by position, moves each definition to the end of the paragraph
holding its reference, and indents it. Only unambiguous pairs get moved.
Everything else is highlighted in the document and listed in
`out.docx.bind-log.txt`, sorted by paragraph order, each line carrying a
searchable snippet of the text, because Word will not show you a paragraph
number. Running it twice changes nothing the second time.

## Design rules

**Structure is decided deterministically.** A model may turn pixels into text.
Whether something is a marker, and which sentence it belongs to, is decided in
code you can audit. A VLM will smooth a year, invent a marker, or complete a
footnote plausibly and wrongly. For a citation, "usually correct" is the most
expensive kind of correct.

**Never guess silently.** The default flags and waits. There will be an
aggressive mode, and it will still record what it did.

**Don't reimplement PDF-to-Markdown.** Marker, MinerU, Docling and olmOCR
exist. Scriptor is meant to orchestrate them behind a narrow backend interface
and refine their output for a use case none of them serves.

**YAGNI**, ranked equal with modularity. Because clean seams make later
extensions cheap, nothing gets built on speculation.

## Where this is going

A real OCR backend behind the existing stub, chosen by testing candidates
against a volume that actually resists. Per-token confidence from that backend,
feeding the same candidate machinery — a backend that reports low confidence on a
superscript glyph knows something the confusion table can only guess. An HTML
review view, since Markdown cannot show colour and the classes want to be told
apart at a glance. A second export profile that hardens page boundaries and
separates the apparatus for chunking and retrieval.

## Layout

```
src/scriptor/
  cli.py                # subcommand dispatcher
  pipeline.py           # end-to-end orchestration
  clippings.py          # journal-clipping path
  pages_zip.py          # Internet Archive page ZIPs
  page.py               # the page model a backend delivers: lines, spans, boxes
  extract/
    pymupdf_backend.py  # text PDFs — reads the text layer, never OCRs
    ocr_backend.py      # stub
  reflow/
    core.py             # reflow, calibration, rendering
    textlines.py        # printed lines, clustered from the fragments a backend reports
    pagelabel.py        # the printed page label (arabic or roman) and its ordinal
    footnotes.py        # marker substitution and rescue
    confidence.py       # candidate search, classification, audit
    decisions.py        # the decision sidecar: accept a candidate, replay the run
    profile.py          # OCR profile: what a corrected corpus says the glyphs are
    prepared.py         # hand-corrected TXT path
    running_elements.py # header/footer detection
    toc.py              # table of contents, preserved and linked
    translation.py      # <dnt> protection, flag stripping
  docx/
    document.py         # minimal OOXML layer over lxml
    footnotes.py        # binding logic
skills/pdf-text-reflow/ # the reflow rules as a Claude skill
tests/fixtures/         # golden files
```

## Related

- [archilles](https://github.com/kasssandr/archilles) — Informed RAG over a
  personal research library: retrieval grounded in page-level citations rather
  than in whatever the chunker happened to keep. Scriptor feeds it.
- [archillator](https://github.com/kasssandr/archillator) — browser-based
  translation of books and academic texts. Scriptor feeds it too, which is what
  `translate-prep` is for.
- [archilles-dictateur](https://github.com/kasssandr/archilles-dictateur) —
  offline push-to-talk dictation.

## License

MIT. See [LICENSE](LICENSE).
