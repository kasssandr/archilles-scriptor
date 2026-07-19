# Authoring ground truth for a real volume

One truth.toml per volume, in eval/golden-local/<id>/truth.toml, next to the
volume's pages/ dir (same layout as eval/golden/synthetic-de). Copyrighted
material never leaves this machine (see eval/README.md).

Procedure per volume — sampling, not completeness:
1. Pick 2–4 probe ranges of 5–10 printed pages each: at least one range with
   dense apparatus, one with a known damage case (e.g. Zuckerman p. 39), one
   boring control range.
2. For every footnote in the probe ranges, record: printed page label,
   printed number, the first ~6 words of the definition
   (definition_starts), the 2–5 words immediately before the true marker
   position (anchor_after; omit when the marker is unreadable in the source
   — status marker_lost), and status:
   - intact: marker clearly printed and legible in the source
   - marker_lost: definition printed, marker invisible/destroyed in source
   - damaged: marker present but corrupted (misprint, broken glyph)
3. pages = the printed labels of the probe ranges only, in order. The
   harness never requires whole-book truth; partial truth over verified
   ranges is the design.
4. Verify against the physical scan (or the PDF at 400% zoom), not against
   any converter output — the truth must be converter-independent.
5. Run: scriptor eval run --truth eval/golden-local/<id>/truth.toml
        --candidate <run>.review.md
   and sanity-check every "misanchored"/"lost" by hand once: a metric bug
   and a real damage look identical until a human has confirmed the first
   few.

Volumes to author, in order (S2 core set):
- zuckerman-1972 (text PDF; the p. 39 hand-resolution case is the reason
  this volume anchors the set)
- baynes-byzantium (scan-derived text; expect lower truth density)
- snell-entdeckung (German typography, footnote-heavy)
- oxford-r3 (ONE paragraph + its bibliography entries, as the first R3
  golden file per ANFORDERUNG §6; citations + bibliography sections in
  truth.toml, footnotes list may stay empty)
