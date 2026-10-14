# Budget and fixed-case figure verification

Updated: 2026-09-25. Backend: Python / matplotlib. Both figures use editable PDF and SVG text and a 600-dpi PNG preview; the manuscript embeds the vector PDF, so no TIFF submission raster is required.

## Budget figure

Question: how does completed search accumulate complete risk evidence while controlling the size of its emitted core?

- Panel a shows Risk-all over all 80 GPT-4o cases at each of the 60 completed-rollout prefixes. Panel b shows the corresponding mean compression, using exactly the same prefix cores and cases.
- The saved rollout events are replayed in completion order with the existing production selector. No inference or resampling is performed. A sentinel client makes any attempted model call fail.
- All 80 final cores match both their frozen result and the canonical main-table selected node lists exactly. The stricter replay check also reproduces final scores, rankings, evidence accumulators, pair memory, core priorities and OC state. All 4,800 case-prefix rows are present.
- The old convergence cache used a separate selector: its final node set differs from the final output for 79 of 80 cases. It is not plotted. The new source table is produced from the replayed production cores, without changing any frozen outputs.
- All plotted means have denominator 80. No bootstrap band or repeated-run uncertainty is inferred from this single frozen benchmark. Every observed prefix is retained; the curve is neither smoothed nor made monotonic.
- One-shot and LEA lines are fixed final reference values. They do not assert budget-dependent trajectories.

| Completed rollouts | Risk-all (%) | Compression (%) |
|---|---:|---:|
| 1 | 2.50 | 81.00 |
| 5 | 25.00 | 65.41 |
| 10 | 65.00 | 58.30 |
| 20 | 76.25 | 54.23 |
| 30 | 73.75 | 52.74 |
| 60 | 75.00 | 51.26 |

Provenance: `gpt4o_budget_verification.json`; all prefix node lists: `gpt4o_budget_case_prefixes.csv`; plotted values: `gpt4o_budget_summary.csv`.

## Fixed-case figure

Question: which evidence does each method retain on the same SCC?

The original Figure 5 case is preserved: Gemini 2.5 Pro, BGB, 25 nodes, handoff invariant, root §505 and witness §491. Stable identity is `scid-v1-2868fa24c421f819a2061cd00c8360703a014afaf105a5e2059f3ae4303b9a69`; case ID is `28_bgb25_scc_3_handoff_invariant`. No new representative-case selection is performed.

The three columns place all 25 clauses on the same 5 × 5 map in canonical order. The figure displays node membership; it does not introduce unobserved topology edges. Diamonds identify the two risk endpoints; retained nodes are colored by evidence category, while omitted nodes remain gray.

| Method | Nodes | Root@3 | Risk-any | Risk-all | Compression |
|---|---:|---:|---:|---:|---:|
| One-shot | 3/25 | 0 | 1 | 0 | 88% |
| LEA | 12/25 | 1 | 1 | 1 | 52% |
| SA-MCGS | 9/25 | 1 | 1 | 1 | 64% |

Provenance and node coordinates: `fixed_case_three_methods_provenance.json`; metrics and selected node lists: `fixed_case_three_methods.csv`.

## QA

| Panel | Role | Summary / unit | Visual checks |
|---|---|---|---|
| Budget a | Complete evidence accumulation | Mean of 80 matched cases | All prefixes plotted; reference lines and SA markers distinct; labels clear |
| Budget b | Core-size cost of evidence | Mean of the same 80 cores | Shared x/y range; final annotation clear; LEA overlap at the final SA value is accurate |
| Case a | Direct-output selection | One fixed case | 25 shared positions; omitted root remains a gray diamond; four metrics and node count visible |
| Case b | Exhaustive local aggregation | Same case/model | Both risk endpoints retained; 12 colored nodes |
| Case c | Search-based compact selection | Same case/model | Both endpoints retained in 9 colored nodes; footer separated from metrics |

Static source audit: 19 pass, no fail; sole warning is the intentionally omitted TIFF. Exported PDF minimum text sizes: budget 7 pt, case 6.4 pt. Both figures were inspected as complete rendered figures and panel by panel. There is no text clipping or collision after adjustment of the case footer spacing. The supplied old PDF assets remain intact for revision history.
