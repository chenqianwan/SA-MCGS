# Scale-gain figure QA

The new compact figure preserves all 30 SA-MCGS minus LEA contrasts: 18 positive, 9 zero, and 3 negative. Positive and negative differences use the same symmetric ±65 pp colour range, without clipping. All cells show a signed value, with exact zero shown as 0.00.

## Data checks

- The 60 underlying absolute proportions agree with independently summed binary metrics in the frozen 1,200-row case table. Both methods use the same case identifiers in each model–scale group.
- Every model retains denominators of 36, 24, and 20 for small, medium, and large SCCs, respectively.
- `scale_gain_cells.csv` contains exact absolute means and percentages, integer numerators and denominators, unrounded differences, and the displayed differences. CSV readback preserves the numeric values exactly.
- Differences are calculated from the unrounded frozen means and then rounded to two decimals. No experiment output is reparsed or regenerated.
- Source-data SHA-256 values and all three old absolute-figure asset hashes are unchanged. Full hashes are in `scale_gain_validation.json`.

## Visual checks

| Panel | Evidence role | Summary | Uncertainty | Labels and collision check | Result |
|---|---|---|---|---|---|
| (a) Root@3 | Localization advantage across SCC size | Difference of fixed-case proportions | Descriptive contrast; no seed interval estimated | 15 cells, every model, all scales and n labels visible; no collision | Pass |
| (b) Risk-all | Complete-evidence advantage across SCC size | Difference of fixed-case proportions | Same convention as panel (a) | 15 cells and shared colour scale visible; no collision | Pass |

The 600-dpi PNG and the PDF rendered at 144 dpi were checked panel by panel and as a complete figure. White background, thin white cell separators, restrained orange–white–blue palette, and consistent Arial text are used. Numeric signs make direction unambiguous in grayscale. Labels remain legible at the native 6.3-inch manuscript width.

## Export checks

- Native dimensions: 6.3 × 2.05 inches, avoiding text reduction when included at the manuscript content width.
- Editable PDF/SVG text; PNG at 600 dpi.
- Source validation: no failures. The generic 89/183 mm width warning is accepted because the exact manuscript width is approximately 160 mm. The missing-TIFF warning is accepted because the publication assets are vector PDF/SVG and PNG is a preview.
- Exported PDF text audit: smallest glyph 7.5 pt; no glyph below 7 pt.
- The original three-method curve assets, existing redraw entry point, manuscript source, and checklists were not modified by this figure task.

Suggested caption: **SA-MCGS gains over LEA across SCC sizes.** Panels show differences in (a) Root@3 and (b) Risk-all, in percentage points. Columns use the same small (≤12 nodes, n=36), medium (14–20, n=24), and large (≥24, n=20) case groups for each model. Blue indicates improvement and orange a decrease; all panels share a zero-centred colour scale.
