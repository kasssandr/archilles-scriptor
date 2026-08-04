# Benchmark corpus: coverage matrix

Volumes are chosen for the properties they carry, not for being at hand. Each
row below is a documented weakness of the pipeline or a variant of the note
apparatus that has to be measured. One volume may serve several rows.

Rows 1–5 are everyday business and get two to three volumes each; rows 6–11
are single phenomena where one witness is enough to catch a regression.

Selection method and per-page rationale live in each band's `selection.json`.
Licence and provenance live in `source.json`. Neither the PDF nor the rendered
pages are committed — `source.json` carries a URL and a SHA-256 so the exact
bytes can be fetched again.

## Rows

| # | Property | Why it is in here | Volumes |
|---|---|---|---|
| 1 | Single-column monograph, page-local footnotes | the ordinary case; the reflow was fitted to one volume (Hechberger) and overfits it | `bauer-aneignung` |
| 2 | Two-column journal typesetting | calibration goes unstable between two issues of one journal (EXCITE 41740 / 41507) | — |
| 3 | Note running over onto the next page | a note variant nothing has ever measured | `bauer-aneignung` (5 marked pages) |
| 4 | Endnotes at chapter or volume end | note variant | — |
| 5 | Mixed apparatus (foot- and endnotes) | standard in critical editions; the hardest case | — |
| 6 | Fraktur, scanned, no textlayer | the Sigilla stress test | — |
| 7 | Right-to-left insertions | Zuckerman; no free substitute yet | — (protected only) |
| 8 | Marginalia and side notes | EXCITE 41507 interleaves body text with a marginal note column | — |
| 9 | Numbered lists in running text | the defect behind commit `0f76b3d`, fixed and currently unguarded | `bauer-aneignung` (p. 88 area) |
| 10 | Running head carrying the page number | Braunfels | `bauer-aneignung` |
| 11 | Non-Latin passages inside Latin typesetting | polytonic Greek, Old English þ ð æ ȝ, scribal abbreviation marks — harder on normalisation than anything in the corpus so far | `mehr-themistios` |

## Licence classes

| Class | Meaning | Where it lives |
|---|---|---|
| `free` | CC-BY, CC-BY-SA, public domain | `eval/corpus/<band>/`, truth committed |
| `restricted` | CC-BY-NC, CC-BY-ND | same, quoted text kept to citation length |
| `protected` | all rights reserved | `eval/golden-local/<band>/`, nothing committed |

**Where the licence comes from matters as much as what it says.** For DOAB and
OAPEN titles the statement frequently exists only in the catalogue record, not
in the PDF — a full-text search for "creative commons" therefore both misses
licensed volumes and turns up unlicensed ones that merely discuss licensing.
Record the evidence in `source.json`.

## Volumes

### bauer-aneignung — rows 1, 3, 9, 10

Bauer, Eva-Maria: *Die Aneignung von Bildern*. Nomos.
doi:10.5771/9783748909576 · CC-BY-4.0 (stated on PDF p. 4) · 348 pages.

19 pages selected: 8 drawn at seed 42 from the body range 19–324, plus 5
pages the operator had marked in the PDF as carrying page-crossing notes —
**and the receiving pages that follow them**. There are 6 of those, not 5: a
sixth overrun sits on drawn page 31, which the operator found while authoring
it, so p032 was added as well.

The receiving pages were an afterthought that turned out to be the point. A
note that breaks off on p. 88 and resumes on p. 89 cannot be measured from
p. 88 alone: whether a converter appends the continuation or files it as a
separate note is only visible on the page that receives it. Row 3 without
receiving pages records the phenomenon without being able to test it.

**Authored and accepted**: 80 notes over 19 pages, 6 of them running over onto
the following page. Every snippet was checked back against the raw textlayer —
each definition follows its own number, each anchor stands on its own page, no
note in the apparatus was missed.

Two things this volume established:

- Its **catalogue labels are off by one** throughout (physical 88 prints "88",
  the catalogue claims "87"). Together with the SSOAR pilot volume, that is
  two out of two volumes where the PDF catalogue is wrong about the printed
  page. The catalogue is a hint in the skeleton, never an answer.
- Its **footnotes run through the whole book** (275, 276, …) rather than
  restarting on each page. `num` records what is printed, page-local or not.
- **It found a defect on its first run.** Where the last line of body text ends
  in a hyphenated word, the first footnote of the page is glued onto the
  fragment: `…die Formensprache bei Baudenkmä275 So hat Raffael…`. The
  continuation ("lern und Skulpturen") waits on the next page and never
  arrives, so the same defect destroys the page-crossing hyphenation as well.
  Measured over the whole volume: **31 of 339 pages, 9 %**. Reproduce with
  `scriptor all` on the source PDF and grep for `[a-zäöüß]{3}\d{1,3} [A-ZÄÖÜ]`.
- What it does get right: the section number `2.`, which sits at x=68 on the
  same baseline y=300 as its heading at x=81, is read *before* the heading.
  Raw PyMuPDF block order puts it after the following paragraph; the baseline
  clustering corrects that.

### mehr-themistios — rows 1, 11

Mehr, Simone: *Ganz Rhetor, ganz Philosoph. Themistios als Lobredner auf
Valens*. De Gruyter. doi:10.1515/9783111013244 · CC-BY-NC-ND-4.0 (stated on
PDF p. 5, so `restricted`) · 273 pages · 8.559 polytonic characters.

11 pages selected: 8 drawn at seed 42 from the body range 15–265, plus the two
densest Greek pages (190 and 198) and p044, which receives an overrunning note.
One of the drawn pages, p041, turned out to be a blank verso between chapters
I and II and was replaced by p024 (replacement seed 43, first free page
carrying text) — a page with no text has no printed number either, and nothing
for a footnote benchmark to measure.

What this volume established:

- **No catalogue labels at all**, on any of its 273 pages — the third volume in
  a row where the PDF catalogue cannot answer what is printed.
- **The numbers in the apparatus are not digits.** De Gruyter's house font sets
  them as private-use glyphs, `U+F131 U+F135` where the page prints 15, with no
  space between number and text. No regex over `\d` will find a definition
  here, and neither will any of Scriptor's three print conventions.
- **Quotations are set in the same size as the notes.** Both are 8.0pt against
  a 9.5pt body; only the indent separates them, about 17 points. On p077 such a
  quotation stands at the foot of the page with nothing below it — exactly
  where the apparatus is expected — and that page carries no note at all. Type
  size alone decides this page wrongly; what saves it today is only that no
  line of the quotation opens with a number.
- **A chapter opening prints no page number.** p178 opens chapter V, where the
  running head is suppressed, so its label 163 is carried on silently. It is
  the one label in this band that was inferred rather than read, kept
  deliberately: a converter has to keep counting here rather than read.
- **Two notes on p178 are word for word identical** (`Amm. 26,6,18.`, notes 5
  and 6). No snippet can tell them apart, which is a problem for the metric,
  not for the truth — see `anchors.py:_find_definition`.
- **Extraction drops spaces between Greek words.** On p. 190 the textlayer
  reads `καὶἐῶμὲν Ὅμηρον καὶἩσίοδον`, where the page prints `καὶ ἐῶμεν Ὅμηρον
  καὶ Ἡσίοδον`. Anyone copying definition text out of `pNNN.txt` would carry
  the defect into the truth and end up measuring the extractor against itself.
  The skeleton now says so.
- The Greek arrives **pre-composed (NFC)**, with 402 of 1.758 characters
  carrying combining marks, some three codepoints deep in NFD (`Ὅ`). That is
  what `normalize.py` assumes, so the assumption now has a witness.
