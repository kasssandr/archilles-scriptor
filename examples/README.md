# A worked example

Two OCR pages of scholarly prose, and what scriptor makes of them. Reproduce it
with:

```bash
scriptor reflow examples/pages --out examples/book.md
```

## What the input looks like

`pages/00000001.txt` is a page as OCR left it — hard line wraps, a page number
on its own line, footnote definitions at the foot:

```
... Fustel de Coulanges1 sah in ihr eine vor allem religioese
Gemeinschaft, waehrend Eduard Meyer& die wirtschaftliche Grundlage ...
1) Fustel de Coulanges, La cite antique, Paris 1864.
6) Ed. Meyer, Geschichte des Altertums, Bd. II, Stuttgart 1893.
7) M. Weber, Wirtschaft und Gesellschaft, Kap. IX, Tuebingen 1922.
12
```

Footnote 6 has a definition but no marker in the body: the superscript 6 after
"Meyer" was read as `&`. This is the failure the whole tool is built around — the
note survives, its anchor does not.

## What a run produces

`book.md` is the clean deliverable. The paragraphs are rebuilt, the page numbers
become inline `[p. 12]` markers, and the page-local footnotes are renumbered into
one document-wide Pandoc sequence. Footnote 6 is not guessed into place: its text
stays as an unreferenced definition (`[^3]`) rather than being attached to the
`&`, and the body reads as valid, translatable Markdown.

`book.review.md` is the same text with the doubt made visible — `Meyer&[?FN:6|&]`.

`book.md.audit.txt` lists every uncertain footnote with its page, its candidate
glyph, and why that glyph scored as it did.

`book.md.decisions.txt` is the file you act on. It has one open line here:

```
[ ] p. 12  fn 6  cand 1  '&'  conf 0.8  ctx: ... waehrend Eduard Meyer& die ...
```

Put an `x` in the box and run the reflow again with
`--decisions examples/book.md.decisions.txt`: the `&` becomes `[^N]` at that
spot, footnote 6 is anchored, and the hanging reference is gone. Leave it empty
and nothing is lost — the definition simply stays unreferenced. The one thing the
tool will not do is decide for you.
