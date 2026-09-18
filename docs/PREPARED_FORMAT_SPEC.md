# The Prepared Document Format

**Version 0.4.0 (draft) · 2026-09-18 · MIT**

This specification defines the *prepared document*: a scholarly text converted
to plain Markdown in which the scholarly apparatus — footnotes, printed page
numbers, bibliographic references — remains machine-readably anchored to the
sentences it belongs to.

The format is the interchange contract of the Archilles tool family
([scriptor](https://github.com/kasssandr/archilles-scriptor) produces it,
[archilles](https://github.com/kasssandr/archilles) indexes it,
[archillator](https://github.com/kasssandr/archillator) translates it), but it
is deliberately tool-neutral: any converter can produce a conforming document,
and any consumer can rely on the guarantees defined here. The specification
currently lives in the scriptor repository, where the format originated; on
publication of the accompanying benchmark it will move, together with the
evaluation harness and golden files, to a standalone repository.

## 1. Purpose and scope

Every mainstream PDF-to-text pipeline treats the scholarly apparatus as noise:
footnote markers vanish, printed page labels are dropped or renumbered, and
short references lose the bibliography that resolves them. Whatever consumes
the output — a retrieval index, a translation model, a human reader — then
works with text whose evidence has been silently destroyed.

A prepared document preserves three things that ordinary Markdown exports do
not:

1. **The printed page as citation address.** Page boundaries survive as inline
   markers carrying the page label *as printed* — a roman-paginated preface
   stays citable as p. xiv.
2. **The footnote as anchored evidence.** Every footnote is a standard Pandoc
   footnote whose marker sits at the sentence that cites it.
3. **Honesty about uncertainty.** Where the conversion could not decide
   something, the doubt is recorded — in a review copy and in sidecar files —
   instead of being resolved by a silent guess.

In scope: the deliverable Markdown, the review copy, the sidecar files, the
do-not-translate convention, citation spans, robustness under user edits, and
documented mappings to TEI and XLIFF. Out of scope: how a producer arrives at
the prepared document (OCR backends, reflow heuristics, extraction quality) —
that is implementation, not format.

## 2. Conformance language

MUST, MUST NOT, SHOULD, and MAY are used as in RFC 2119. A **producer** is any
tool that writes prepared documents. A **consumer** is any tool that reads
them. Requirements marked **(reserved)** define syntax that is normative but
not yet emitted by the reference implementation; producers MUST NOT use the
reserved syntax for other purposes.

## 3. The document set

For a deliverable named `book.md`, the full set is:

| File | Role | Required |
|---|---|---|
| `book.md` | **Deliverable.** Clean Pandoc Markdown, never carries flags. | yes |
| `book.review.md` | **Review copy.** Same text plus inline uncertainty flags. | if uncertainty exists |
| `book.md.audit.txt` | **Audit sidecar.** One block per uncertain footnote: page, class, candidates, reasons; plus a run summary. | if uncertainty exists |
| `book.md.decisions.txt` | **Decision sidecar.** The still-open choices, one checkbox line per candidate. | if open choices exist |
| `book.md.pagination.json`, `.txt` | **Pagination sidecar.** Where every page label came from (§6.3). | if pages carry markers |
| `book.md.structure.json`, `.txt` | **Structure sidecar.** The volume's division as the producer read it (§6.5). | if headings are marked |
| `book.translate.md` | **Translation profile.** Deliverable with `<dnt>` protection applied. | on demand |
| `book.translate.briefing.txt` | **Briefing sidecar.** Instructions for the translating model. | with the translation profile |

The deliverable is self-contained: a consumer that reads nothing but `book.md`
MUST still get a valid, complete document. Sidecars add information; they never
carry text that is missing from the deliverable.

## 4. The prepared Markdown

### 4.1 Base format

A prepared document is UTF-8 Pandoc Markdown. The deliverable MUST be valid
Pandoc Markdown at all times — this is the load-bearing guarantee from which
everything downstream (translatability, chunkability, further conversion)
follows.

A document MAY open with a YAML metadata block, in Pandoc's
`yaml_metadata_block` syntax — `---`, the fields, a closing `---`, then the
text:

```yaml
---
format_version: 0.4.0
chunking_strategy: basic
pagination: bottom edge, 95% of pages attested
structure: 3 levels, chapters on level 1, 48 headings (45 contents, 3 numbering)
---
```

| Field | Meaning |
|---|---|
| `format_version` | The version of *this* specification the producer targeted. |
| `chunking_strategy` | How a retrieval consumer should cut the text: `basic` cuts semantically and may drop the apparatus; `scientific` keeps a footnote marker and its definition in one chunk. |
| `pagination` | How far the page markers of this document can be trusted: which edge the volume paginates at, and the share of pages whose label something corroborated rather than merely asserted. Free text, meant to be read; the machine-readable form is the sidecar of §6.3. |
| `structure` | How the producer read the volume's division: how many depths, which depth carries the chapters, how many headings and where they came from. Free text, meant to be read; the machine-readable form is the sidecar of §6.5. |

`pagination` exists because a marker cannot carry its own provenance. `[p. 47]`
looks the same whether the page printed the number or the converter counted it
out of the sequence, and a consumer weighing a citation cannot tell them apart
from the text. The share is not the share of *labelled* pages: a volume can be
labelled throughout by counting on from a single reading, which is a different
thing from a volume whose numbers are witnessed.

The block is optional, and every field in it is optional. Consumers MUST
tolerate its absence, MUST ignore fields they do not know, and MUST NOT
require it — a document without the block is conforming, and defaults to
`basic`.

Two properties make this block safe to add to a format whose contract is
plain text. It is *declaration only*: nothing in it may contradict the text,
and no text may live only here (§4.6 applies unchanged — a consumer that
discards the block still gets the whole document). And it is *machine
address, not content*: it carries what a consumer must be told, never what a
reader must read.

`format_version` is what the block exists for. A prepared document outlives
the release notes that describe it — it sits in an index for years — so a
consumer meeting it later must be able to learn which conventions were in
force when it was written, from the document and nothing else.

### 4.2 Page markers

A page boundary is recorded inline, at its reading position, as:

```
[p. LABEL]
```

- `LABEL` is the page label **as printed in the book** — arabic (`211`), roman
  (`xiv`), or whatever the volume uses. It MUST NOT be renumbered, translated,
  or normalised to physical PDF page indices. `p.` is an invariant token of the
  format, not a localisation; consumers MUST NOT expect `[S. …]` or other
  localised variants in a conforming document.
- `LABEL` MUST NOT contain `]` or a line break.
- The marker stands in running text exactly where the page break falls;
  a paragraph that spans a page break carries the marker mid-paragraph. A page
  whose break falls between paragraphs carries it at the start of the following
  block.
- Consumers MUST treat the marker as the citation address of all following text
  up to the next marker.

A heading that opens a page stands before that page's marker: the marker is
not pulled into the heading, and the marker that opens the following block
addresses the heading as well. Consumers resolving the page of a heading SHOULD
take the marker of the block that follows it.

Where a table of contents was recognised, the first occurrence of a page marker
that is a TOC target additionally carries a Pandoc anchor:

```
[p. 211]{#p-211}
```

The anchor id is `p-` plus the label, verbatim. TOC entries link to these
anchors with standard Markdown links. Consumers MAY use the anchors; they MUST
NOT require them.

### 4.3 Footnotes

Footnotes use standard Pandoc syntax: `[^N]` at the anchor, `[^N]: text` as
the definition. Two rules extend Pandoc:

- **Document-wide numbering.** `N` is a positive integer, unique across the
  whole document. Printed footnote numbers restart per page or chapter;
  prepared documents renumber globally because Pandoc footnote ids must be
  unique. The printed (page-local) number is recoverable through the audit
  sidecar, which is keyed by printed page label and printed footnote number.
- **Definitions at the document end.** All `[^N]:` definitions are collected
  at the end of the document, in anchor order.

**Hanging references.** A footnote definition whose marker could not be located
in the body is not dropped and not attached to a guess. It is preserved as a
regular footnote with a **synthetic anchor** (a plain definition without an
anchor would be silently discarded by Pandoc renderers, which is exactly the
data loss this format exists to prevent). The synthetic anchor is placed at
the **upper bound of the interval in which the lost marker can lie** — the
last position at which it could still legally stand:

1. immediately **before the next confidently placed footnote anchor**, when
   that anchor lies on the same printed page;
2. otherwise at **the end of the printed page's own text**: at the end of the
   paragraph in which the page's body text ends or, when that paragraph
   continues across the page boundary, immediately before the following
   `[p. …]` marker.

Several hanging references sharing the same bound are placed there together,
in ascending printed-number order. The rule is deterministic — no judgement
call between candidate paragraphs — and it preserves three invariants at
once: the ascending marker order (a synthetic anchor never overtakes a placed
marker), the citation address (the anchor stays on the page whose apparatus
it belongs to, so resolving by the nearest preceding page marker (§4.2) gives
the printed page on which the note appeared), and reading order (the anchor
appears only after every sentence it might have belonged to). That the anchor
is synthetic — “somewhere on this page before this point, exact position
unknown” — is recorded in the audit sidecar, keyed by printed page and
printed footnote number.

### 4.4 Headings and structural regions

**Headings.** A heading the producer recognised is an ordinary Markdown ATX
heading, `#` to `######`.

- The heading text is the volume's own text as printed where the heading
  stands. The printed designator — `A.`, `I.`, `3.4`, `Erstes Kapitel:` — is
  part of the heading text and MUST be kept verbatim: never added, renumbered,
  translated or normalised by the producer. A heading that wraps in print is
  one heading line here.
- Depth is the heading's depth in the volume's own division: `#` is the
  coarsest level on which the body is divided (parts where the volume has
  parts, otherwise chapters), `##` the level below, and so on. A region title
  the volume lists beside its chapters — a bibliography, a preface — is a
  heading at the depth the volume gives it. Packaging (cover, half title,
  imprint, a bare ISBN) is never a heading.
- Depth is nesting, not rank. Which depth carries the chapters is a property of
  the volume, stated in the structure sidecar (§6.5) and in the `structure`
  field of the metadata block (§4.1). Consumers MUST NOT read `#` as
  "chapter"; they MAY read depth as nesting and MUST tolerate a jump in depth
  (`###` directly after `#`).
- A volume may divide deeper than Markdown can spell. A heading below the sixth
  depth is written `######`; where its printed designator does not tell it
  from the sixth, the producer MAY set its text in emphasis (`###### *…*`).
  Its true depth is carried by the structure sidecar (§6.5); a consumer reading
  the document alone reads it as the sixth depth, and one comparing heading
  texts SHOULD disregard an emphasis around the whole of the text.
- A producer MUST NOT insert a heading whose words the source does not print at
  that place, and MUST NOT remove a line that prints a heading's title. A
  running head that repeats a title is furniture and may go; the heading it
  repeats stays. Where the producer cannot tell the two apart, the line stays
  as text and no heading is marked: an unmarked heading is running text, which
  is the safe direction (see *Absence of a marker is not a claim* below).
- The rebuilt table of contents (treatment below) lists every entry with its
  printed designator; entries link to the page anchors of §4.2.
  **(Reserved)** A heading MAY carry a Pandoc identifier `{#…}`; consumers
  MUST ignore an identifier they do not use, and the translation profile MUST
  carry it over unchanged.

**Regions.** Beyond running prose, a prepared document treats regions
differently in two respects — how their text is set, and what they are called.

The **treatment** is a producer matter and needs no markup:

- **Front matter** (title pages, imprint) is preserved line-faithfully, block
  per page, behind its page marker.
- **Table of contents** is rendered as link lines targeting the page anchors
  (§4.2).
- **Entry regions** (bibliography, index, abbreviation lists) are reflowed one
  entry per block, page markers preserved between entries.

The **name** is a consumer matter, and it is marked. Where the producer knows
which region it is in, it says so; a region opens with a marker on a line of
its own:

```
[region: bibliography]
```

- The marker governs **all following text up to the next region marker** or
  the end of the document — the same reach rule as the page marker (§4.2), so
  a consumer that already resolves page markers needs no second mechanism.
- It stands as its own block, separated by blank lines. It never appears
  inline, and never inside a paragraph, a heading or a footnote definition.
- Where a region begins at a page boundary, the region marker precedes the
  page marker: the region is the wider frame, and the page marker belongs to
  the text it introduces. A region that begins mid-page opens before the first
  block that belongs to it, leaving the page marker where §4.2 puts it.
- A region a heading opens — a heading whose title names the region — opens
  immediately before that heading: the region marker precedes the heading
  line. A heading whose title names no region does not end the region it
  stands in.
- `NAME` is one of the values below. It is an invariant token of the format,
  never localised and never translated.

| `NAME` | The region |
|---|---|
| `front-matter` | Title pages, imprint, dedication. |
| `contents` | Table of contents. |
| `preface` | Preface, foreword, acknowledgements — what a book says about itself before it begins. Named so a consumer can weigh it; never apparatus, because a preface that leads into the argument is a chapter. |
| `main` | Running text — the body the book is about. |
| `bibliography` | Bibliography, list of sources, works cited. |
| `index` | Index of any kind — names, subjects, places, passages. |
| `abbreviations` | List of abbreviations or sigla. |
| `notes` | A collected notes section (endnotes at the end of a chapter or volume), as distinct from the footnotes of §4.3. |
| `appendix` | Appendices, tables, documentary supplements. |

**Absence of a marker is not a claim.** A document may carry no region marker
at all; a region the producer could not identify simply stays unmarked.
Consumers MUST treat unmarked text as `main`, and MUST tolerate a `NAME` they
do not know by treating it the same way — an unrecognised region is an
unknown, and an unknown is running text.

This asymmetry is deliberate and is the rule producers MUST follow when
deciding whether to mark at all: *a wrongly marked apparatus is an
annoyance, a wrongly marked chapter is silent loss.* An index that surfaces
in a search is visible and can be ignored. A chapter classified as apparatus
disappears from retrieval, and nobody notices it is gone. **When in doubt,
emit no marker.**

`main` is a value like any other, and it is how a document returns to running
text after an apparatus region — a volume whose appendix is followed by
further chapters marks those chapters `main` again.

### 4.5 Escaping

Literal `*` and `_` in the source text are backslash-escaped, so that OCR
artefacts can never toggle Markdown emphasis and silently swallow characters.
The format's own constructs (`[^N]`, `[p. …]`, `[region: …]`, leading `#`,
flags, `<dnt>`) never contain these characters; the one emphasis the format
sets itself is the one around a heading below the sixth depth (§4.4).

### 4.6 The deliverable guarantee

The deliverable MUST NOT contain uncertainty flags (§5) or unresolved
placeholder syntax of any kind. Doubt is expressed in the review copy and the
sidecars — never in the deliverable, whose contract is: *always translatable,
always chunkable, always valid Pandoc* (“strip and pass”). An unresolved
footnote appears in the deliverable as a hanging reference (§4.3), which is
valid Pandoc; the open question about it lives in the sidecars.

### 4.7 Addressing a passage

A passage of a prepared document is addressed by three things the document
itself carries: the volume, the printed page the passage stands on (§4.2), and
a short run of its own wording. Where a volume prints the same label more than
once — a volume in parts restarts its numbering — the address names which
occurrence of the marker is meant, counted from the start of the document;
where a label occurs once, the occurrence is 1 and MAY be omitted. A note is
addressed by the page its anchor stands on and the number printed beside it
(§6.6), never by its document-wide `[^N]` id, which is renumbered whenever the
document is produced again.

The wording is the check, not the pointer. A consumer resolving an address
MUST locate the page by its marker first and only then search for the wording
within that page, normalised the way a sidecar's context snippet is matched
(§9). Where the wording is not found on that page the address is stale (§9)
and MUST be reported, not repaired by searching elsewhere; a consumer MAY offer
the nearest page that carries the wording as a proposal, marked as such.
Nothing in an address depends on a consumer's own state: chunk identifiers,
character offsets and physical page numbers are caches that speed a lookup up
and whose loss invalidates nothing.

The volume, the page, the occurrence and the note are invariant under
translation (§7); the wording is not. A consumer holding a translated document
resolves the page and the note and treats the wording as belonging to the
source.

## 5. Confidence flags (review copy only)

The review copy is the deliverable text plus inline flags at the exact
positions where the producer was uncertain. Flag syntax (chosen so that
`\[\?\??FN:` is greppable and cannot collide with `[^N]` or `[p. …]`):

| Class | Meaning | Syntax |
|---|---|---|
| certain | Marker present, sequence intact. | no flag |
| suggested | Exactly one plausible candidate glyph. | `[?FN:6\|&]` after the glyph |
| guessed | Several candidates, or weak evidence. | one `[??FN:6\|&:0.7]` per candidate, each at its own position |
| orphan | Definition exists, no candidate found. | `[?FN:6]` at the end of the page's text (placement rule of §4.3) |

- The number after `FN:` is the **printed, page-local** footnote number — the
  flag talks about the page as scanned, so a human can check it against the
  original in seconds.
- The character after `|` is the raw glyph at the candidate position; the
  number after the second `:` (guessed class only) is a confidence in
  `0.0`–`1.0` with one decimal digit.
- `[?ital]` before an emphasis span is **(reserved)** for uncertain italics.
- Flags MUST be removable by deleting the bracketed expression (plus one
  optional preceding space); what remains MUST be the deliverable text. This
  is the strip-and-pass property, and it is what makes the review copy safe to
  hand to any Pandoc-speaking tool after manual cleanup.

## 6. Sidecars

Sidecars are plain UTF-8 text, designed to be read by humans and diffed by
git. They are keyed by what the page prints — **printed page label + printed
footnote number or heading text + context snippet** — never by byte offset, so
they survive edits that do not touch the passage they describe (§9).

### 6.1 Audit sidecar (`*.md.audit.txt`)

A run summary header (`#`-prefixed lines: page count, certain/uncertain
footnote counts, conventions), then one line per uncertain footnote:

```
p. 6: FN 2 [guessed]  ->  z:0.9 (word-end, confusion z→2, seen 6x), Z:0.7 (word-end, confusion Z→2)
```

Every candidate carries its score and the reason it was scored that way; every
rejection is recorded with its reason. The audit is the complete, replayable
justification of the producer's decisions — the property the format calls
*auditability*.

### 6.2 Decision sidecar (`*.md.decisions.txt`)

One checkbox line per open candidate:

```
[ ] p. 6  fn 2  cand 1  'z'  conf 0.9  seen 6x  ctx: …bore the mintZ or the mintz mark and the die [3]…
```

A human answers by putting `x` in the box; the producer replays the run with
the decisions applied and regenerates the file, which shrinks as work
proceeds. Marking two candidates for one footnote MUST be refused, not
resolved by picking one. An empty box loses nothing: the footnote stays a
hanging reference.

### 6.3 Pagination sidecar (`*.md.pagination.json` and `*.md.pagination.txt`)

Where the audit sidecar justifies the footnotes, this pair justifies the page
markers. Both are written from one verdict, so they cannot disagree with each
other or with the document.

The **JSON** is the machine channel:

```json
{
  "version": 1,
  "profile": {"edge": "bottom", "attested": 0.95, "inherited": 0.004,
              "band": [0.944, 0.968]},
  "segments": [{"start_pos": 13, "start_label": "XI", "style": "roman-upper",
                "kind": "counted"}],
  "pages": [{"pos": 13, "label": "XI", "source": "printed", "confidence": 1.0}],
  "rejected": [{"pos": 12, "label": "177", "source": "printed-bottom",
                "verdict": "contents-page", "predicted": "X", "sample": "Pág."}]
}
```

`source` is the strongest witness that confirmed the label:

| Value | Meaning |
|---|---|
| `printed` | the page states the number itself |
| `link` | a contents entry the producer linked to this page states it |
| `toc` | the contents names the page and the entry's title was found here |
| `catalogue` | the PDF's own PageLabels |
| `computed` | nobody observed it; it follows from the numbering alone |

The first two **corroborate**, the rest **assert**; only those two count towards
`attested` (§4.1). Consumers SHOULD carry `source` into whatever they build on
the marker — a citation resting on a computed label is usable but weaker — and
MUST tolerate values they do not know, treating them as asserted. The list has
grown twice and will grow again.

`profile.inherited` is the share of the volume's text, notes included, that is
cited as another page. A page with no label gets no marker, so its text runs on
under the label of the last page that had one (§4.2), and neither the document nor
`pages` shows it — only the producer can count it. Text before the first labelled
page is not included: it has no address, which is not the same as a wrong one. A
consumer deciding whether to trust a volume's page references reads it next to
`attested`, because the two fail apart: a volume can witness most of its numbers
and still cite half its text as a page it is not on, where the numbers it
witnessed stop. Sidecars written before the field existed lack it; a consumer MUST
read its absence as unknown, never as zero.

`pages[].pos` is the channel for the physical page: the ordinal, in the source,
of the page whose label the marker prints. The document carries no marker of
its own for it, by design — the marker is the citation address, and there is
one. Consumers wanting the physical page SHOULD take it from here and MUST NOT
derive it from the marker sequence, which cannot count the pages that carry no
marker.

**(Reserved)** `profile.reference` names the edition the labels refer to where
the producer took them from a declaration rather than from the page — an EPUB
page-list with its `dc:source` — as `{"declared_by": …, "value": …}`. Such
labels carry `source = catalogue`.

`rejected` records readings the numbering overruled, with what they were instead.
An overruled reading is not necessarily a wrong one: where the model cannot
represent what the volume does — a stretch one page long, a sheet carrying two
book pages — the reading is sound and the model is what cannot follow it.

The **text** file is the same verdict for a reader, ordered by position in the
document, every entry quoting a line that can be searched for.

### 6.4 Determinism and replay

The decision loop presupposes a deterministic producer: the same input pages
and the same decisions MUST reproduce the same output, certain choices
untouched. Producers whose extraction stage is non-deterministic (VLM OCR)
MUST confine the non-determinism to the extraction layer and keep structure
decisions — what is a marker, what anchors where — deterministic and audited.

### 6.5 Structure sidecar (`*.md.structure.json` and `*.md.structure.txt`)

Where §6.3 justifies the page markers, this pair justifies the headings. Both
are written from one reading of the volume, so they cannot disagree with each
other or with the document.

The **JSON** carries one record per `#` line of the document, in document
order — the list a consumer walks beside the document's own headings:

```json
{
  "version": 1,
  "chapter_level": 1,
  "schemes": [{"scheme": "word-ordinal", "depth": 1, "count": 4},
              {"scheme": "letter-upper", "depth": 2, "count": 9}],
  "headings": [{"depth": 2, "designator": "A.", "scheme": "letter-upper",
                "title": "Die Handschriften", "page": "14", "pos": null,
                "anchor": null, "region": null,
                "sources": [{"source": "contents", "why": "placed by rule 2"}]}],
  "unplaced": [{"text": "III. Der Anhang", "page": "90"}],
  "rejected": [{"text": "1. Die These", "page": "112", "reason": "not-in-contents"}]
}
```

`chapter_level` is the depth on which this volume opens its chapters.
`schemes` is the ordered list of numbering schemes the volume uses and the
depth each stands on, as learnt from its contents. Each heading gives its true
`depth` (past the sixth, too — §4.4), its printed `designator` and the
`scheme` it belongs to, its `title` without the designator, the printed label
of the `page` it stands on, `pos` for the physical page where known, `anchor`
where a producer places by location rather than by page (an EPUB target),
`region` where the heading opens one, and `sources`, the witnesses that placed
it, each with the reason — empty where nothing but the document itself stands
behind the heading. `unplaced` lists contents entries whose title was found on
no page (nothing was inserted for them); `rejected` lists lines the producer
declined to read as headings, each with its reason.

`source` is a vocabulary that grows like `source` in §6.3: `contents`,
`outline`, `numbering`, `typography`, `running-head`; `stale` for a heading
that stands in the document but that no witness of this reading names — one a
user wrote or changed by hand; for EPUB producers `nav`, `heading-tag`,
`epub-type`. Consumers MUST tolerate values they do not know.

The **text** file is the same reading for a reader: the tree indented in
document order, one searchable line per heading, then the scheme table, then
the unplaced and rejected entries.

Records are keyed by printed page label and heading text, never by offset
(§9). A heading is identified by the page it stands on and its wording, never
by its position in this list: an edit that inserts a heading moves every
position after it and no page or wording at all. A consumer using a record
MUST verify it against the document first; a heading the user has re-levelled
or reworded makes its record stale, and a stale record is flagged, not
applied. `chapter_level` MAY be recomputed from the headings by a consumer
whose sidecar is stale; the rule is shared code, not a guess.

### 6.6 Notes sidecar (reserved)

**(Reserved.)** A future producer writes `*.md.notes.json`: one record per
footnote, carrying the document-wide id `N`, the printed label and occurrence
of the page its anchor stands on, the number printed beside it, and the
physical position of that page. It is written from the pass that numbers the
definitions, so it cannot disagree with the document. A consumer that needs
the printed number behind `[^N]` — a reader checking against the volume, a
link into the apparatus — reads it here; the audit sidecar (§6.1) lists only
the notes the producer was unsure of. Until it is written, `[^N]` is a cache
valid for one production of the document.

## 7. The do-not-translate convention (`<dnt>`)

The translation profile protects text that must survive machine translation
verbatim — bibliographic references, work titles, URLs — with one marker pair:

```
<dnt>Römische Geschichte</dnt>
```

Normative rules:

1. **Syntax.** `<dnt>` … `</dnt>`, literal, ASCII, no attributes. The pair
   MUST NOT nest and SHOULD NOT span a paragraph boundary.
2. **Translator contract.** Text inside the pair MUST pass through translation
   character-for-character: never translated, reordered, or normalised.
3. **Removability.** After translation, stripping every `<dnt>` and `</dnt>`
   token (keeping the enclosed text) MUST restore a well-formed document.
   Stripping is a pure string operation; no state is needed.
4. **Idempotence.** Applying dnt protection to an already protected document
   MUST NOT double-wrap: producers MUST NOT open a new span inside an existing
   one.
5. **Scope of protection.** The reference producer currently tags URLs
   (everywhere) and quoted titles (on footnote definition lines). The set of
   protected elements MAY grow (notably R4 primary-source references, §8);
   the syntax is fixed.
6. **Structural markers are protected by contract, not by tags.** `[^N]`,
   `[^N]:`, `[p. …]` and `[region: …]` are never wrapped; the accompanying
   briefing sidecar obliges the translator to carry them over unchanged. A
   page label may be roman (`[p. xiv]`); it is the page as printed and MUST
   never be renumbered by translation. A region name is an invariant token and
   MUST NOT be translated, even where the surrounding heading is.

The briefing sidecar (`*.briefing.txt`) is the human/model-readable statement
of rules 2, 3 and 6 plus the soft instruction for what no rule can catch
(untagged titles in running footnote prose: when in doubt, do not translate).
The end-to-end guarantee this convention exists for: **a citation address
survives translation.**

## 8. Inline citation spans (reserved)

Scholarly citation takes more forms than the footnote apparatus. The format
names five regimes: **R1** footnote apparatus (§4.3), **R2** endnotes and
mixed apparatuses, **R3** author-year short references inline
(`(Aerts 2003, 25–54)`, narrative `Aerts (2003)`), **R4** primary-source
references against canonical systems (`Dio Chrys., Or. 36.16–17`,
`1 Cor 13:12`, `CIL VI 1234`), **R5** short-title and cross-reference chains
(*ibid.*, *op. cit.*, “see n. 12”). R3 and R4 anchor as spans; this section
norms their syntax ahead of implementation, so that later producers do not
each invent one.

A recognised reference is marked with a Pandoc bracketed span that keeps the
**original wording as its content**:

```
[Aerts 2003, 25–54]{.cit type=r3 ref=aerts2003}
[Dio Chrys., Or. 36.16–17]{.cit type=r4}
```

- The visible text is the reference exactly as printed — source-truth over
  convenience. Machine data lives only in the attributes. A consumer that
  strips attributes (or a human reading the raw file) loses nothing of the
  text.
- `type` is the regime (`r3`, `r4`). `ref` (R3 only) is the key of the
  resolved entry in the bibliography sidecar; it is present only when the
  reference resolved against the book's own bibliography with certainty.
  Resolution is book-internal: `ref` never points outside the document set.
- Unresolved or uncertain candidates are **never** marked in the deliverable —
  the text stays untouched, and the doubt appears as a flag in the review copy
  (`[?CIT:…]`, grammar analogous to §5) and as a record in the sidecar. A
  reference the bibliography does not know remains prose, not markup. The
  deliverable guarantee (§4.6) applies unchanged.
- The translation profile MUST protect `.cit` spans of type `r4` as `<dnt>`
  (a primary-source reference is never translated) and SHOULD protect the
  span content of type `r3`.

The bibliography itself stays out of the running text (it is an entry region,
§4.4) and is parsed into a sidecar: one table per bibliography section (books
carry split and multiple bibliographies), each entry a key, the raw entry
string, and optional structured fields; plus an occurrence table mapping each
span to its entry with a confidence class. The sidecar file format follows the
conventions of §6 and will be fixed when the first producer implements it;
the *span syntax above is fixed now*.

## 9. Robustness under user edits

Prepared documents live in working vaults — Obsidian, git checkouts, editors.
**A user edit is the normal case, not a failure mode.** The format's anchors
are chosen to degrade gracefully:

- **Self-contained anchors survive.** `[p. LABEL]` markers, footnote anchors
  with their definitions, `.cit` spans and `<dnt>` pairs carry their meaning
  in the text itself; moving a paragraph moves its anchors with it, and
  nothing outside the paragraph breaks.
- **A damaged region marker fails towards running text.** Region markers open
  a span rather than enclose one (§4.4), which is why an edit cannot invert
  their meaning: delete `[region: index]` and the index reads as `main` — the
  harmless direction. There is no closing token whose loss could pull the rest
  of the volume into an apparatus region, and no way for one broken marker to
  reach beyond the next one.
- **A heading line is self-contained.** Depth, designator and title stand in
  the line; re-levelling, deleting or adding a heading changes the division
  consistently and nothing else. Only the sidecar's record for that heading
  goes stale (§6.5).
- **Sidecar keys are positional only at the last step.** Sidecar records key
  by page label + footnote number + context snippet (§6). A consumer using a
  sidecar record MUST verify it before acting on it: locate the page by its
  marker, then match the context snippet. If the snippet no longer matches,
  the record is **stale**.
- **Stale means flag, not guess.** A consumer holding a stale record MUST NOT
  apply it heuristically; it MUST surface the discrepancy (flag, log, refuse —
  whatever its idiom is) and continue without the record. This is the same
  ethic the producer follows at conversion time, one stage later.
- **Validity is checkable without sidecars.** A prepared document with broken
  Pandoc footnote pairing (anchor without definition or vice versa) after an
  edit is detectable by any Pandoc parser; consumers SHOULD report it rather
  than repair it silently.
- **(Reserved)** A future sidecar version will add per-page checksums over
  normalised page text, making drift detection O(1) instead of snippet
  matching. The invalidation rule stays as defined here.

## 10. Export mappings (specified, not implemented)

The prepared document is the working format; it does not compete with archival
and industry standards. These tables document how its constructs map — they
are the proof that nothing in the format is an island. Implementations follow
demand.

### 10.1 TEI

| Prepared | TEI |
|---|---|
| `[p. 211]` | `<pb n="211"/>` |
| `[p. 211]{#p-211}` | `<pb n="211" xml:id="p-211"/>` |
| `[^4]` + `[^4]: text` | `<note place="bottom">text</note>` inline at the anchor position |
| hanging reference | `<note place="bottom" anchored="false">text</note>` |
| `#`-heading | `<head>` within the corresponding `<div>` |
| `[…]{.cit type=r3 ref=k}` | `<bibl corresp="#k">…</bibl>` |
| `[…]{.cit type=r4}` | `<bibl type="primary">…</bibl>` |
| `<dnt>…</dnt>` | not needed (no MT context); representable as `<seg type="dnt">` |
| review-copy candidates | `<unclear>`/`<choice>` with `@cert` |

The combination that matters — footnotes moved to their marker *and* printed
page labels on page breaks — has a TEI precedent in the Bibliotheca
Hertziana's *trans2tei* (2021), which this mapping follows in spirit.

### 10.2 XLIFF

| Prepared | XLIFF 2.x |
|---|---|
| `<dnt>…</dnt>` | `<mrk translate="no">…</mrk>` |
| `[p. 211]`, `[^4]` | `<ph>` inline placeholder codes (protected, position-stable) |
| footnote definition | its own `<segment>` |
| briefing sidecar | `<notes>` on the file element |

## 11. Versioning

The specification uses semantic versioning. Within a major version, documents
remain parseable by older consumers: new constructs are additive, and
everything reserved in §4.4, §5, §6, §8 and §9 is claimed syntax that will only ever
mean what this document says. Breaking changes (marker syntax, flag grammar,
dnt convention) require a major version bump — and are a family event, not a
local commit: every consuming tool tests against this document, and a change
here is coordinated across all of them before release.

The region vocabulary of §4.4 grows additively: a minor version MAY add a
`NAME`, and older consumers stay correct because an unknown name reads as
running text by rule. Removing or redefining a name is breaking.

0.3.0 adds `preface` and narrows `front-matter`, which until then covered
preface matter as well. Additive by that rule: a consumer that does not know
the name treats it as running text, which is what a preface should get anyway.

0.3.0 also adds the `pagination` field (§4.1) and the pagination sidecar
(§6.3). Additive on the same terms: the field is optional and the sidecar is a
separate file, so a consumer that knows neither reads the document exactly as
before. The `source` vocabulary of §6.3 grows the way the region names do — it
has gained two values since it was introduced, and a consumer meeting an
unknown one MUST treat it as asserted rather than fail.

0.4.0 defines what 0.3.0 left open: what the depth of a heading means, that
the printed designator belongs to the heading text, and that a producer never
inserts or deletes a heading's words (§4.4). Additive by the rules above: a
consumer that read `#` as a chapter keeps working and is merely told, now,
that it was reading nesting. 0.4.0 also adds the `structure` field (§4.1), the
structure sidecar (§6.5), the heading-before-marker rule (§4.2) and
`pages[].pos` as the channel of the physical page (§6.3) — all optional, all in
separate files or fields, so a consumer that knows none of them reads the
document exactly as before. It states the address of a passage (§4.7), which
adds no syntax: it says what a consumer may rely on when it cites, from the
markers and the text that were there already. And it reserves the notes
sidecar (§6.6) and `profile.reference` (§6.3).

Producers SHOULD state the spec version they target, in the document's
`format_version` field (§4.1) and in tool `--version` output. Until version
0.2.0 the document carried no version of its own and the specification
pointed at release notes instead; that does not survive contact with an
archive, where a file is read years after the notes that described it. What
remains of the original intent is narrower and still holds: the metadata
block declares, it never narrates. Everything a human reads is text, and a
consumer that drops the block loses no word of the document.

## 12. Consumer guarantees

What each family tool may rely on, stated once:

- **Retrieval (archilles).** Stable page boundaries with printed labels for
  page-level citations; body and apparatus separable (footnote definitions
  collected at the document end); regions named where the producer knows them
  (§4.4), so an index or a bibliography need not be recognised again by the
  consumer; no flags, no layout artefacts in the deliverable. A search hit can
  therefore always cite the printed page. What the producer does *not* mark is
  running text — the guarantee is that a region marker is never a guess, not
  that every apparatus carries one. Where the provenance of a page label
  matters, it is in the sidecar of §6.3 rather than in the marker: the marker
  is the same string whoever produced it; the physical page travels there too,
  as `pages[].pos`. Headings nest, and the depth that carries the chapters is
  declared rather than assumed (§4.4, §6.5). A consumer citing a passage
  SHOULD emit the address of §4.7 — page, occurrence, wording — rather than an
  identifier of its own index, so that the citation resolves against the
  document alone.
- **Translation (archillator).** `<dnt>` protection per §7; structural markers
  carried over by briefing contract; strip rules that restore a clean target
  document. A citation address therefore survives translation.
- **Humans.** The review copy and the decision sidecar contain every doubt the
  producer had, each with its candidates and reasons — correcting a flagged
  glyph is a two-second job, and nothing was ever guessed silently on the way.
