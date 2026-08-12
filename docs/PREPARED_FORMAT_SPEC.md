# The Prepared Document Format

**Version 0.3.0 (draft) · 2026-08-12 · MIT**

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
format_version: 0.3.0
chunking_strategy: basic
---
```

| Field | Meaning |
|---|---|
| `format_version` | The version of *this* specification the producer targeted. |
| `chunking_strategy` | How a retrieval consumer should cut the text: `basic` cuts semantically and may drop the apparatus; `scientific` keeps a footnote marker and its definition in one chunk. |

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

Chapter and section headings recognised by the producer are ordinary Markdown
`#` headings. Beyond running prose, a prepared document treats regions
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
flags, `<dnt>`) never contain these characters.

### 4.6 The deliverable guarantee

The deliverable MUST NOT contain uncertainty flags (§5) or unresolved
placeholder syntax of any kind. Doubt is expressed in the review copy and the
sidecars — never in the deliverable, whose contract is: *always translatable,
always chunkable, always valid Pandoc* (“strip and pass”). An unresolved
footnote appears in the deliverable as a hanging reference (§4.3), which is
valid Pandoc; the open question about it lives in the sidecars.

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
git. They are keyed by **printed page label + printed footnote number +
context snippet** — never by byte offset, so they survive edits that do not
touch the passage they describe (§9).

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

### 6.3 Determinism and replay

The decision loop presupposes a deterministic producer: the same input pages
and the same decisions MUST reproduce the same output, certain choices
untouched. Producers whose extraction stage is non-deterministic (VLM OCR)
MUST confine the non-determinism to the extraction layer and keep structure
decisions — what is a marker, what anchors where — deterministic and audited.

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
everything reserved in §5, §8 and §9 is claimed syntax that will only ever
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
  that every apparatus carries one.
- **Translation (archillator).** `<dnt>` protection per §7; structural markers
  carried over by briefing contract; strip rules that restore a clean target
  document. A citation address therefore survives translation.
- **Humans.** The review copy and the decision sidecar contain every doubt the
  producer had, each with its candidates and reasons — correcting a flagged
  glyph is a two-second job, and nothing was ever guessed silently on the way.
