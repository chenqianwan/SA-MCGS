# Budget and fixed-case figure review

The two figures now use a restrained Nature-style composition within the existing manuscript's 6.3-inch double-column measure. All quantitative inputs, selected clauses, and coordinates are unchanged. The new rendering code reads only the frozen summaries; it neither reconstructs experiments nor invokes a model.

## Panel review

| Panel | Evidence role | Statistic and unit | Uncertainty | Visual review |
|---|---|---|---|---|
| Budget a | Complete risk evidence with increasing search budget | Frozen Risk-all over the same 80 cases at each of 60 saved prefixes | No repeated-run interval supplied or inferred | All 60 values shown without smoothing; clear axes, endpoint label, and reference lines; pass |
| Budget b | Core compactness accompanying the evidence gain | Frozen mean compression over the same 80 cases | Same descriptive-aggregate treatment | All 60 values shown; endpoint annotation clears the One-shot reference; pass |
| Case a | One-shot comparison on the fixed instance | 25 node positions, 3 retained nodes, five recorded indicators | Not applicable to this single fixed case | Missing root remains visible as an open diamond; all node labels and metrics legible; pass |
| Case b | LEA comparison on the same instance | Same positions, 12 retained nodes, five recorded indicators | Not applicable | Both risk endpoints clearly retained; no fabricated edges; pass |
| Case c | SA-MCGS selection on the same instance | Same positions, 9 retained nodes, five recorded indicators | Not applicable | Both risk endpoints retained with a smaller core; same geometry and metric rows; pass |

## Appearance and export

- White background, Arial, dark text/axes, restrained gray/orange/blue method palette.
- Budget baselines use open circle/square legend marks and distinct line styles; SA-MCGS uses a filled triangle. The line shapes remain distinguishable in grayscale.
- Case selection is encoded with fill as well as method color; endpoint identity uses a diamond outline. No category depends on hue alone.
- Lowercase bold panel labels; shared legend; no ornamental frames, cards, stripes, or duplicated metric prose.
- Budget canvas: 6.3 × 2.2 inches; case canvas: 6.3 × 3.34 inches.
- PDF glyph audits: minima 7.0 pt and 6.5 pt respectively; no text outside the canvas.
- PDF and SVG text are editable. PNG previews are 600 dpi (3780 × 1320 and 3780 × 2004 pixels).
- Each panel and the assembled figures were inspected after export, including 120-dpi previews at the final physical dimensions. No text/mark collisions or clipping remain.
- Data SHA-256 values are unchanged before and after rendering. The budget retains all 60 rows; each case panel retains all 25 clauses and five summary values.

## Automated preflight notes

The source validator reports no failures. Its two warnings are expected: the manuscript's exact 160.02 mm measure takes precedence over the skill's generic 89/183 mm defaults; PDF/SVG are the publication assets and a PNG preview was requested, so an additional TIFF is unnecessary.

## Caption alignment

The budget caption can remain scientifically unchanged; its horizontal comparisons remain final One-shot and LEA references. The case caption should describe filled nodes as retained, open nodes as omitted, and diamonds as the root/witness risk endpoints, with gray/orange/blue distinguishing the methods. The prior affected-context color description should be removed. The clause map contains no graph-edge claims.
