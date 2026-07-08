"""An OCR profile: what glyph the superscript digits of a *corpus* look like.

Within one volume the evidence is free — count the glyphs that stand in its own
sequence gaps (``confidence.collect_evidence``). Across volumes there is nothing
to count: a fresh book has no gaps yet. What carries over is what a human already
confirmed, and that lives in the decision sidecars.

So a profile is built from decision files and read back as an explicit input:

    scriptor learn a.md.decisions.txt b.md.decisions.txt --out corpus.json
    scriptor reflow pages/ --out book.md --ocr-profile corpus.json

Explicit, because the alternative destroys the property the whole correction loop
rests on. A table that grew as a side effect of past runs would make the same
pages yield different candidates tomorrow than today. As a file it is data: the
same pages plus the same profile plus the same code give the same decision file.
This is KONZEPT_scriptor_v2.md §9 Q5 taken literally — regenerate the data table,
leave the logic alone.

Two evidence qualities, kept apart on purpose. A document count says "this glyph
once stood in a gap", which the confusion table itself proposed. A profile entry
says "a human confirmed this glyph *is* that digit". The profile therefore enters
scoring as a small number of pseudo-observations (§ ``PSEUDO_WEIGHT``): enough to
rank a book that has no evidence of its own, never enough to outvote a book that
does. A volume's own typography beats the corpus average, because it is the same
scan, the same typeface, the same engine.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from scriptor.reflow.decisions import AmbiguousDecision, read_lines

SCHEMA_VERSION = 1

# How many observations a profile is worth per digit, spread over the glyphs a
# human accepted. Set to the threshold at which a document is believed at all, so
# a profile alone just reaches it and any real evidence immediately outweighs it.
PSEUDO_WEIGHT = 3.0


@dataclass
class GlyphRecord:
    accepted: int = 0   # a human chose this glyph as the lost marker
    rejected: int = 0   # it was offered beside the glyph the human chose


@dataclass
class OcrProfile:
    glyphs: dict[int, dict[str, GlyphRecord]] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return any(r.accepted for gs in self.glyphs.values() for r in gs.values())

    def digits(self) -> list[int]:
        return sorted(self.glyphs)

    def pseudo_counts(self, weight: float = PSEUDO_WEIGHT) -> dict[tuple[int, str], float]:
        """``weight`` observations per digit, split by the share of confirmations.

        A glyph that was only ever rejected contributes nothing and so falls to the
        prior floor — which is the demotion the rejections were evidence for.
        """
        out: dict[tuple[int, str], float] = {}
        for digit, records in self.glyphs.items():
            confirmed = sum(r.accepted for r in records.values())
            if not confirmed:
                continue
            for glyph, record in records.items():
                if record.accepted:
                    out[(digit, glyph)] = weight * record.accepted / confirmed
        return out


def learn(sources: Iterable[tuple[str, str]]) -> OcrProfile:
    """Build a profile from decision files, given as (name, text) pairs.

    A pure function of its inputs: pass the same files and get the same profile,
    so nothing can be counted twice by running the command again. To add a volume,
    list it alongside the others rather than appending to an existing file.

    Within one footnote, the marked candidate is a confirmation and every other
    candidate offered for it is a rejection. A footnote nobody marked says nothing
    either way and is skipped — undecided is not the same as refused.
    """
    profile = OcrProfile()
    for name, text in sources:
        profile.sources.append(name)
        by_footnote: dict[tuple[str, int], list] = {}
        for line in read_lines(text):
            by_footnote.setdefault(line.ref, []).append(line)

        for (page, fn), lines in by_footnote.items():
            marked = [ln for ln in lines if ln.marked]
            if not marked:
                continue
            if len({ln.cand for ln in marked}) > 1:
                raise AmbiguousDecision(
                    f"{name}: footnote {fn} on page {page} has two candidates marked; "
                    f"mark exactly one"
                )
            chosen = marked[0]
            records = profile.glyphs.setdefault(fn, {})
            for ln in lines:
                if ln.glyph is None:
                    continue  # a line written before glyphs were recorded
                record = records.setdefault(ln.glyph, GlyphRecord())
                if ln.cand == chosen.cand:
                    record.accepted += 1
                else:
                    record.rejected += 1
    return profile


def dumps(profile: OcrProfile) -> str:
    """Stable JSON: sorted keys, so a profile diffs cleanly in version control."""
    payload = {
        "version": SCHEMA_VERSION,
        "sources": profile.sources,
        "glyphs": {
            str(digit): {
                glyph: {"accepted": r.accepted, "rejected": r.rejected}
                for glyph, r in sorted(profile.glyphs[digit].items())
            }
            for digit in sorted(profile.glyphs)
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def loads(text: str) -> OcrProfile:
    payload = json.loads(text)
    version = payload.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported OCR profile version {version!r}")
    glyphs = {
        int(digit): {
            glyph: GlyphRecord(rec.get("accepted", 0), rec.get("rejected", 0))
            for glyph, rec in records.items()
        }
        for digit, records in payload.get("glyphs", {}).items()
    }
    return OcrProfile(glyphs=glyphs, sources=list(payload.get("sources", [])))


def load(path: str | Path) -> OcrProfile:
    return loads(Path(path).read_text(encoding="utf-8"))


def save(profile: OcrProfile, path: str | Path) -> None:
    Path(path).write_text(dumps(profile), encoding="utf-8")
