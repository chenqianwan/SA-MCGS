# Scale-gain heatmap contract

The figure asks where SCC size changes SA-MCGS's advantage over LEA. Panel (a) establishes the root-localization contrast and panel (b) tests whether that contrast extends to complete risk evidence. Both panels retain every requested model and size group. The previous three-method absolute curves remain a separate appendix asset.

- Archetype: compact quantitative grid; two aligned 5 × 3 panels.
- Data: existing frozen model–method–scale aggregates, cross-checked against the frozen 1,200-row case table. No outputs are reparsed and no experiment is rerun.
- Mapping: `model` → fixed row order; `scale` → ≤12, 14–20, ≥24 nodes; `root_at3` and `risk_all` → panel metrics. Each cell is `100 × (SA-MCGS mean − LEA mean)` in percentage points, computed before display rounding.
- Counts: 36, 24, and 20 case variants per model and method. Numerators and metric denominators are exported along with absolute values and differences.
- Coverage: all 30 requested cells, including all zero and negative differences. No model or scale filtering beyond the explicitly requested SA-versus-LEA comparison.
- Style: Python/matplotlib; Arial; white background; a shared orange–white–blue scale symmetric around zero. Blue denotes an increase, orange a decrease. Colour limits cover all values without clipping.
- Export: 6.3 × 2.05 inches, matching the manuscript content width without font reduction; editable PDF/SVG; 600-dpi PNG; every rendered glyph ≥7 pt.
- Statistics: descriptive contrasts of the existing fixed case groups; no seed uncertainty or significance tests are introduced.
- Integrity: source SHA-256 values checked before and after, exact case-level sums and denominators checked against the existing aggregates, all plotted values exported to CSV. The old figure, original source data, and redraw entry points are left unchanged.
