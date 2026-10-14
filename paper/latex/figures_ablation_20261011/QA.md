# Capacity-gain figure QA

**PASS — final size 85 × 32 mm.** All 12 requested comparisons are shown.

Figure contract: one quantitative grid tests whether the Risk-all advantage of
dynamic replacement over locked selection persists across four core-capacity
settings. The three rows are model strata, not independent replicate studies.
Python/matplotlib is the sole plotting backend. White background, a continuous
zero-anchored blue scale from 0 to 30 percentage points, direct numerical labels,
and a thin outline for the prespecified 45% default avoid significance encoding.

## Data and interpretation

- Each cell subtracts locked-matched-k Risk-all from Full Risk-all at the same
  capacity, using all 80 cases from 20 source SCCs for its model.
- Each comparison receives the same observed search trajectory and matches
  Full's actual endpoint core size. A capacity setting is an upper bound;
  it does not imply that every returned core has exactly that size.
- All 12 values are positive. Rows Llama / Qwen / Kimi, columns 25 / 35 / 45 / 60%:
  `[11.25, 22.50, 27.50, 15.00]`, `[25.00, 22.50, 23.75, 18.75]`,
  `[10.00, 6.25, 5.00, 7.50]` percentage points.
- One trajectory per model-case; four injected variants share each source SCC.
  Values are descriptive paired differences, with no repeated-run uncertainty
  or significance claim. No data exclusions, smoothing, or fitted values.
- Original aggregate values, all case IDs, and source hashes are preserved in
  `source_data.json`. The displayed labels round only to two decimal places.

## Automated and visual checks

- `source_preflight.json`: 18 PASS, 0 FAIL. The two WARN findings are accepted:
  TIFF is outside the requested PDF/SVG/PNG export contract; the static validator
  cannot resolve the millimetre-size constants, but the exported PDF measures
  85.0000 × 32.0000 mm.
- `pdf_text_audit.json`: 25 editable text runs; minimum 6 pt, none below 5 pt.
  SVG text remains text; PDF uses embedded TrueType fonts.
- Production PNG is exported at 600 dpi. PDF/SVG have the same exact canvas,
  without tight cropping. The separately rendered `qa_final_size_150dpi.png`
  is for physical-size visual inspection only.
- Single-panel audit: all row/column labels fit, numeric labels stay inside
  their own cells, default outline clears numbers, and colorbar/tick labels
  do not collide. Every text bounding box lies inside the canvas.
- Compact revision: each heatmap row is 5.55 mm high; cell values remain 7.2 pt,
  model/column/axis labels 7 pt, and colorbar ticks 6 pt. The colorbar title
  sits beside the bar to remove a text row without shrinking glyphs.
- Numeric labels preserve interpretation in grayscale or without color.
  The default outline denotes a parameter setting, not statistical evidence.

## Reproduction

Runtime used: Python 3.11, matplotlib 3.10.8, NumPy; Arial font.

```sh
python build_capacity_gain.py --source-data source_data.json
```

Alternatively, `--values PATH` regenerates the portable source data directly
from the full experiment tables. The default input resolves relative to the
repository. Outputs are `capacity_gain.pdf`, `.svg`, and `.png` in this directory.

## Caption suggestion

Risk-all gain from dynamic replacement over locked selection across core
capacities. Each cell is a paired difference in percentage points on 80 cases
per model, using shared trajectories and matched output sizes. The outlined
column marks the default 45% capacity.
