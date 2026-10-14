# Five-model assets: validation and visual review

All 1,200 accepted method rows are retained: 5 models × 80 stable variant IDs × 3 methods. The 80 variants correspond to 20 source SCCs. Each of the 60 displayed main-table values reproduces the accepted two-decimal percentage. No inference or output re-parsing was performed. Source file hashes are checked and the three accepted summary files remain unchanged.

The canonical data preserve source-specific missing measurements without imputation. Aggregates retain per-metric counts in machine-readable columns. The descriptive figures and tables use these existing accepted summaries. The scale figure uses all 36 short, 24 mid, and 20 long variants per model; the domain and scale tables pool the same five models. The full model-by-domain and model-by-scale breakdowns are also exported.

## Figure contract and visual audit

| Panel | Evidence role | Summary and unit | Audit |
|---|---|---|---|
| Scale top row: all five models | Root localization across original SCC size | Mean Root@3 over all variants in each size bin | Five panels checked: common 0–100 ticks, all three methods visible, readable titles and no collisions |
| Scale bottom row: all five models | Complete risk retention across original SCC size | Mean Risk-all over the same size bins | Five panels checked: same method palette and shapes, shared scale; no clipped marks |
| Coverage–compression: all five models | Joint coverage and compression achieved by each method | Three accepted aggregate points per model | Five panels checked: shared 0–100 axes, no point masking, no arrows or invented trajectories |

These are descriptive frozen-benchmark summaries rather than repeated-seed estimates, so no inferential error bars or significance tests are introduced. Curves connect ordered size categories; marker offsets separate ties within a category. One-shot is gray/circle, LEA orange/square, and SA-MCGS blue/triangle. The new figures inherit only style and physical dimensions from the existing Python workflow; their data mapping and aggregation are rebuilt explicitly.

PDF/SVG exports contain editable text. The two figure PDFs have a minimum text size of 6 pt. PNGs are 320 dpi inspection previews; the manuscript uses the vector PDFs, so source-preflight warnings about optional 600 dpi TIFF delivery do not apply. The remaining uncertainty warning is a keyword heuristic addressed by the descriptive-summary definition above. Automated source preflight has no failures.

## Table layout

The supplementary table compiles independently without overfull boxes. Its model block sits above domain and scale blocks arranged side by side. Text is 7.5 pt (smallest math glyph about 6.97 pt), and every row was inspected visually. The generated file contains the table environment and `tab:appendix_breakdowns`, with no revision-color markup.
