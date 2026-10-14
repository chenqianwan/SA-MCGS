# Heatmap candidate design

Both figures answer how SA-MCGS changes the accepted performance profile. They use the same fixed five models and existing aggregate means; no experiment is rerun and no observations or categories are removed.

- **B — gains against the two baselines.** Two complementary controls distinguish the change from One-shot from the additional change over LEA. Each control contains every model and all four metrics, for 40 cells. This is an overview of the accepted outcome profile.
- **C — where complete-risk gains occur.** The left panel decomposes the SA-MCGS minus LEA Risk-all difference by domain; the right decomposes it by SCC size. All 35 cells remain visible. The figure localizes variation that the aggregate table cannot show.

Both are quantitative grids, drawn only with Python/matplotlib at 6.3 inches wide. A common symmetric diverging colour scale is fixed at ±70 percentage points only after asserting it covers every displayed value. Warm colours denote decreases; blue denotes increases; near-white denotes equality. Every cell is annotated, including zero and negative values. Differences are computed from the frozen unrounded means, then rounded to two decimal places for display.

Exports are editable-text PDF and SVG plus 600-dpi PNG. Arial text has a 7.3-point minimum. Numerical means are descriptive summaries of the fixed case set, not independent seed estimates; no uncertainty intervals or significance tests are invented. Case and metric denominators from the source are retained in the exported cell data. Source and output data hashes are recorded and rechecked. The final panels and complete figures will be visually inspected.
