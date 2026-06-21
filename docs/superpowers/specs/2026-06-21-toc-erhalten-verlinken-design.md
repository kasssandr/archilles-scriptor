# Spec: TOC erkennen, erhalten & seiten-verlinken

**Datum:** 2026-06-21
**Status:** Genehmigt, bereit für Implementierungsplan
**Kontext:** Nacharbeit #3 aus `memory/offene-nacharbeiten.md`

## Problem

Heute erkennt der Reflow ein Inhaltsverzeichnis (TOC) nur, um es **wegzuwerfen**:
`render_toc` (`src/scriptor/reflow/core.py:664`) gibt unabhängig vom Inhalt nur
`["[Inhaltsverzeichnis ausgelassen]"]` zurück. Das TOC ist damit die einzige
Region, die aktiv verworfen wird — Frontmatter, Bibliografie und Register
bleiben verbatim erhalten (`render_frontmatter` core.py:653,
`render_entries` core.py:671).

Zwei Lücken:

1. **Erkennung** ist minimal: einziger Trigger ist das exakte, versale,
   alleinstehende deutsche Heading `^INHALTSVERZEICHNIS\s*$`
   (`HEADING_TRIGGERS` core.py:277). Fremdsprachige oder heading-lose TOCs
   werden nie als `toc`-Region erkannt.
2. **Erhaltung** fehlt ganz: erkannte TOCs werden gelöscht statt bewahrt und
   navigierbar gemacht.

Ziel: TOC **mehrsprachig/strukturell erkennen**, **erhalten** und — wo die
Datenlage es sicher zulässt — **seiten-basiert verlinken** (klickbar in
Pandoc-HTML/EPUB, analog zu den Fußnoten-Ankern).

## Realitäts-Befund (prägt das Design)

Reales OCR liefert TOCs oft als **mehrspaltiges Layout, das die OCR
spaltenweise statt zeilenweise gelesen hat**. Beispiel Baynes
*„Byzantium; an introduction"*, Seite `00000011.txt`: erst ein Block mit
allen Kapiteltiteln, dann — physisch getrennt — ein Block mit allen
Seitenzahlen (`XV / I / 33 / 51 / 71 / 86 …`). Titel und Seitenzahl sind
**nicht Zeile für Zeile gepaart**.

Konsequenzen:

- Das Kriterium „Zeile endet auf eine Seitenzahl" greift bei zerrissenem
  Input nicht.
- Eine zuverlässige Titel↔Seitenzahl-Zuordnung ist aus solchem Input nicht
  gewinnbar; jedes Pairing wäre Raten.
- Mehrspalten-Entzerrung ist bewusst **out of scope** (eigene Etappe #2 /
  Bresson, siehe `memory/offene-nacharbeiten.md`). Diese Spec entzerrt
  **nicht**, sie erkennt nur, ob sie sicher pairen kann, und erhält sonst
  verbatim.

Das folgt dem Projekt-Leitbild (Konzept v2): **ehrliche Confidence-Behandlung
statt Raten**.

## Designentscheidungen (vom Nutzer bestätigt)

| # | Entscheidung | Wahl |
|---|---|---|
| 1 | Scope | Erhaltung **+** strukturelle (heading-lose) Erkennung **+** mehrsprachige Headings |
| 2 | Verlinkung | **Seiten-basiert** (`[S. NN]` → Anker), unabhängig von der lückenhaften Heading-Erkennung |
| 3 | TOC-Format (sauberer Fall) | **Verlinkte Markdown-Liste mit Hierarchie** |
| 4 | Erkennungsreichweite | Frontmatter-Phase **und** Dokumentende |
| 5 | Confidence-Gate | sauber gepaart → verlinkte Liste; unsicher → **verbatim erhalten** + ehrlicher Marker, nie Rate-Links |

## Architektur

### Neues Modul `src/scriptor/reflow/toc.py`

`core.py` ist bereits groß; die gesamte TOC-Logik wird in ein fokussiertes
Modul ausgelagert. `core.py` ruft es an genau drei Stellen auf. Öffentliche
Schnittstelle von `toc.py`:

- `is_toc_page(page, *, min_entry_lines=4, page_end_fraction=0.6) -> bool`
  — struktureller Klassifikator (Schritt-2-Erkennung).
- `detect_trailing_toc(pages) -> None` — Nachlauf, der End-TOCs umklassifiziert.
- `parse_toc(pages) -> TocParse` — extrahiert Einträge + misst Pairing-Konfidenz.
- `render_toc(pages) -> TocRender` — liefert die gerenderten Blöcke **und** die
  Liste der Ziel-Seitenzahlen für die Anker-Injektion.

Datenklassen:

```python
@dataclass
class TocEntry:
    title: str
    page: int          # gedruckte Seitenzahl laut TOC; -1 wenn keine
    level: int         # 1-basiert; 1 = oberste Ebene

@dataclass
class TocParse:
    entries: list[TocEntry]
    confidence: float  # 0.0-1.0, Pairing-Güte

@dataclass
class TocRender:
    blocks: list[str]
    anchor_targets: set[int]   # leer im verbatim-Fallback
```

### Erkennung (drei Wege, Priorität absteigend)

**(a) Heading-Trigger, mehrsprachig.** In `HEADING_TRIGGERS` (core.py:277) wird
das TOC-Pattern ersetzt durch eine case-insensitive Alternation als
**alleinstehende Zeile**:

```
INHALTSVERZEICHNIS | INHALT | CONTENTS | TABLE OF CONTENTS |
TABLE DES MATIÈRES | SOMMAIRE | INDICE | SOMMARIO | ÍNDICE
```

Bewusst ausgelassen: das mehrdeutige bloße `INDEX` (de/en = Register, nicht
TOC) — Register laufen weiter über die `raw`-Trigger.

**(b) Strukturell heading-los** (`is_toc_page`). Eine Seite gilt als TOC-artig,
wenn von ihren nicht-leeren Body-Zeilen
ein Anteil ≥ `page_end_fraction` (Default 0.6) auf eine **plausible
Seitenzahl** endet (1–4 Ziffern am Zeilenende, optional nach Leader-Punkten/
Whitespace) **und** mindestens `min_entry_lines` (Default 4) solcher Zeilen
existieren. In `assign_modes` (core.py:326) greift dieser Test **nur, solange
`mode in ("frontmatter",)`** — nicht im laufenden `main`-Text (vermeidet False
Positives im Fließtext).

**(c) Trailing-TOC** (`detect_trailing_toc`). Ein separater Pass **nach**
`assign_modes`: von der letzten Seite rückwärts werden zusammenhängende
TOC-artige Seiten (per `is_toc_page` oder End-Heading-Treffer) von `main` →
`toc` umklassifiziert, bis eine nicht-TOC-artige Seite den Lauf beendet.
Deckt die dt./frz./ital. Tradition des TOC am Bandende ab.

> **NACHTRAG (nach Schluss-Review, 2026-06-21): (c) wurde wieder entfernt.**
> Der heading-lose Trailing-Pass stützte sich allein auf `is_toc_page` und
> klassifizierte numerische Back-Matter (engl. Index/Chronologie ohne
> `raw`-Trigger) fälschlich als TOC — mit geratenen Links, was dem
> Confidence-Leitprinzip widerspricht. Entscheidung: Trailing-Erkennung ganz
> entfernt; TOC wird nur noch in der Frontmatter-Phase (a/b) erkannt. End-TOC
> bleibt offene Nacharbeit (nur mit Heading-Bestätigung wieder einführbar).

### Confidence-Gate (`parse_toc`)

Pro `toc`-Seitengruppe werden Einträge zeilenweise geparst. Eine Zeile ist
„sauber gepaart", wenn sie nach Abtrennen von Leader/Whitespace in
`Titel … <Seitenzahl>` zerfällt (nichtleerer Titel + abschließende 1–4-stellige
Zahl).

```
confidence = clean_paired_lines / non_empty_lines
```

verschärft durch einen **Monotonie-Bonus/Malus**: sind die geparsten
Seitenzahlen überwiegend nicht fallend, bleibt die Konfidenz; viele
Rückwärtssprünge senken sie. Ist `confidence ≥ TOC_LINK_THRESHOLD`
(Default **0.7**, modulkonstante, kalibrierbar) → verlinkter Pfad, sonst
verbatim-Fallback.

Baynes (Titel- und Zahlenblock getrennt) ⇒ die meisten Zeilen enden **nicht**
auf eine Zahl ⇒ `confidence` niedrig ⇒ verbatim.

### Rendering (`render_toc` neu)

**Hohe Konfidenz** → verlinkte Markdown-Liste mit Hierarchie. Verschachtelung
**primär aus der Nummerierung** (`1.` → Ebene 1, `1.1` → Ebene 2, …; gleiche
Logik wie `heading_level` core.py:404), **sekundär aus führender Einrückung**;
bei Unsicherheit **flach**. Pro Eintrag mit Body-Marker ein Link, Einrückung
zwei Leerzeichen je Ebene:

```
## Inhaltsverzeichnis

- [Die Krise](#p-15) — S. 15
  - [Vorgeschichte](#p-18) — S. 18
- [Der Wandel](#p-42) — S. 42
```

`anchor_targets` sammelt die referenzierten Seitenzahlen (nur die mit Link).

**Niedrige Konfidenz** → verbatim erhalten (Originalzeilen pro Seite, mit
`[S. NN]`-Marker, analog `render_frontmatter`), eingeleitet von einem ehrlichen
Marker:

```
[Inhaltsverzeichnis: verbatim erhalten — Verlinkung wegen unsicherer Spaltentrennung ausgelassen]
```

`anchor_targets` ist hier leer.

### Seiten-Anker (Post-Processing, Golden-Schutz)

`render_book` (core.py:728) sammelt die `anchor_targets` aller TOC-Gruppen.
**Nach** dem Zusammenbau des Dokuments und **nur im md-Format** injiziert ein
Post-Schritt an das **erste** Vorkommen von `[S. NN]` jeder Ziel-Seite den
Pandoc-Anker:

```
[S. 42]  →  [S. 42]{#p-42}
```

Eigenschaften:

- Nur Ziel-Seiten werden angefasst; alle übrigen `[S. NN]` bleiben unverändert.
- Existiert für eine TOC-Seitenzahl **kein** Body-Marker, wird der betreffende
  TOC-Eintrag bereits in `render_toc` **ohne Link** gerendert (ehrlich), und die
  Zahl landet nicht in `anchor_targets`.
- Bände **ohne** TOC erzeugen leere `anchor_targets` ⇒ kein Post-Schritt ⇒
  Output **byte-identisch** zu heute (Hechberger-Golden geschützt).
- `txt`-Format bleibt ankerfrei.

Pandoc-Span-Syntax `[…]{#id}` ist zulässig, da das Deliverable Pandoc-Markdown
ist (`.pandoc.md`, cli.py:133) und Pandoc-Footnotes bereits genutzt werden.

> **Smoke-Test bestätigt (2026-06-21, pandoc 3.10):** Echtes Pipeline-Markdown
> → HTML rendert `[S. NN]{#p-NN}` zu `<span id="p-NN">` und `[Titel](#p-NN)` zu
> `<a href="#p-NN">`; jeder Link trifft sein Anker-Ziel, Hierarchie bleibt
> erhalten, keine ID-Kollision, keine pandoc-Warnung. Die seiten-basierte
> Verlinkung funktioniert real in HTML/EPUB.

## Modulinteraktion (Zusammenfassung)

```
assign_modes (core.py)
  ├─ HEADING_TRIGGERS  ← (a) mehrsprachige Headings
  └─ is_toc_page       ← (b) strukturell, nur in frontmatter-Phase   [toc.py]
detect_trailing_toc (core.py ruft toc.py)  ← (c) End-TOC-Pass        [toc.py]
render_book (core.py)
  └─ für mode == "toc":  render_toc(group)  → TocRender              [toc.py]
       └─ parse_toc → confidence-Gate → Liste|verbatim
  └─ nach Zusammenbau (fmt == "md"): inject_page_anchors(doc, targets)
```

## Tests

- **Fixture Baynes-TOC** (`00000011.txt`, ggf. Folgeseite) → erwartet
  verbatim-Fallback + Marker, `anchor_targets == ∅`, keine Rate-Links.
- **Synthetische saubere einspaltige TOC-Fixture** → erwartet verlinkte
  Hierarchie-Liste **und** injizierte `{#p-NN}`-Anker am ersten passenden
  `[S. NN]`.
- **Hechberger-Golden byte-identisch** (Regressionsschutz: kein TOC ⇒ keine
  Anker ⇒ keine Änderung).
- **Units** in `tests/test_toc.py`:
  - `is_toc_page`: positiv (sauberes TOC), negativ (Prosaseite, Bibliografie).
  - `parse_toc`: Konfidenz hoch (einspaltig) vs. niedrig (Baynes-artig
    getrennt); Monotonie-Effekt.
  - Hierarchie: Nummerierung `1./1.1`, Einrückungs-Fallback, flacher Fallback.
  - `inject_page_anchors`: nur erstes Vorkommen, nur Ziel-Seiten, md-only,
    fehlender Marker ⇒ kein Anker.

## Nicht in Scope (YAGNI)

- Mehrspalten-/Spalten-Entzerrung des TOC selbst (eigene Etappe #2/Bresson).
- Heading-basierte Verlinkung (TOC-Titel → Body-Überschrift). Body-Headings
  werden heute nur numeriert erkannt (`heading_level` core.py:404); Fuzzy-Match
  ist fehleranfällig und wurde zugunsten der seiten-basierten Anker verworfen.
- Reflow/Glättung der TOC-Titel über Zeilenumbrüche hinweg im verbatim-Fall.

## Offene Defaults (kalibrierbar, keine Blocker)

- `TOC_LINK_THRESHOLD = 0.7`
- `is_toc_page`: `page_end_fraction = 0.6`, `min_entry_lines = 4`
- Marker-Text des verbatim-Falls (Wortlaut oben als Vorschlag).
