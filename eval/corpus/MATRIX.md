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

13 pages selected: 8 drawn at seed 42 from the body range 19–324, plus 5
targeted pages the operator had marked in the PDF as page-crossing notes.

Two things this volume established:

- Its **catalogue labels are off by one** throughout (physical 88 prints "88",
  the catalogue claims "87"). Together with the SSOAR pilot volume, that is
  two out of two volumes where the PDF catalogue is wrong about the printed
  page. The catalogue is a hint in the skeleton, never an answer.
- Its **footnotes run through the whole book** (275, 276, …) rather than
  restarting on each page. `num` records what is printed, page-local or not.

### mehr-themistios — rows 1, 11

Mehr, Simone: *Ganz Rhetor, ganz Philosoph. Themistios als Lobredner auf
Valens*. De Gruyter. doi:10.1515/9783111013244 · CC-BY-NC-ND-4.0 (stated on
PDF p. 5, so `restricted`) · 273 pages · 8.559 polytonic characters.

10 pages selected: 8 drawn at seed 42 from the body range 15–265, plus the two
densest Greek pages (190 and 198).

What this volume established:

- **No catalogue labels at all**, on any of its 273 pages — the third volume in
  a row where the PDF catalogue cannot answer what is printed.
- **Extraction drops spaces between Greek words.** On p. 190 the textlayer
  reads `καὶἐῶμὲν Ὅμηρον καὶἩσίοδον`, where the page prints `καὶ ἐῶμεν Ὅμηρον
  καὶ Ἡσίοδον`. Anyone copying definition text out of `pNNN.txt` would carry
  the defect into the truth and end up measuring the extractor against itself.
  The skeleton now says so.
- The Greek arrives **pre-composed (NFC)**, with 402 of 1.758 characters
  carrying combining marks, some three codepoints deep in NFD (`Ὅ`). That is
  what `normalize.py` assumes, so the assumption now has a witness.
