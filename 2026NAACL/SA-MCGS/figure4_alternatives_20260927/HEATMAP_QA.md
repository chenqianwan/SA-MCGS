# Heatmap candidate QA

## Data and comparison

- B includes all 40 requested cells: 28 positive, 6 zero, 6 negative.
- C includes all 35 requested cells: 24 positive, 5 zero, 6 negative.
- All five models retain the agreed order. No category or metric is filtered.
- Every difference is calculated from the frozen unrounded means, multiplied by 100, then displayed to two decimals. Compression uses the accepted mean and its existing denominator. Source denominators are preserved alongside every exported cell.
- Both figures share the same zero-centred colour map and symmetric ±70 pp limits. An assertion checks that every value is in range; no clipping is used.
- Both CSV files were read back and compared with the in-memory numeric values exactly. Source SHA-256 was unchanged before and after generation. Per-file hashes and counts are in the validation JSON.

## Panel-by-panel inspection

| Panel | Evidence role | Summary | Uncertainty | Labels and geometry | Result |
|---|---|---|---|---|---|
| B-a | Overall gain against One-shot | Difference of fixed aggregate means | Descriptive comparison; no new interval estimated | All 20 signed values and four metrics visible | Pass |
| B-b | Additional gain beyond LEA | Difference of fixed aggregate means | Same as B-a | All 20 signed values, including +0.05 compression, visible | Pass |
| C-a | Domain-specific complete-risk gain | Risk-all mean difference | Descriptive strata; no new interval estimated | All 20 values, all domains, and case counts visible | Pass |
| C-b | Scale-specific complete-risk gain | Risk-all mean difference | Same as C-a | All 15 values, all size groups, and case counts visible | Pass |

Figures were inspected panel by panel in the high-resolution exports and in PDF renders at 144 dpi. No overlaps, clipped labels, illegible cells, or escaped text were found. Numeric annotations preserve meaning in grayscale. The exact sign is shown even for small differences whose colour is nearly white.

## Export checks

- Editable PDF/SVG text; Arial; smallest exported PDF glyph 7.3 pt in each figure.
- B: 6.3 × 2.83 inches. C: 6.3 × 2.98 inches. These use the current manuscript's approximately 160 mm content width, so the generic 89/183 mm source-preflight width warning is intentionally inapplicable.
- PNG previews: 600 dpi. PDF/SVG are the publication assets; the generic warning that no TIFF was exported is accepted for these vector-only quantitative figures. Rendering and QA use Python only.
- Source validation has no failures. Exported-PDF glyph audits pass with no warnings and no text under 7 pt.
- No existing manuscript source or previously selected asset was changed.
