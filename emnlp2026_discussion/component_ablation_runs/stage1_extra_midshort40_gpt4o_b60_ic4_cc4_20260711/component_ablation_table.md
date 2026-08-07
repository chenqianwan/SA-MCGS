# Stage 1 Component Ablation Main Table

Main run: 20 matched cases. Full SA-MCGS rows are copied from locked main results; LLM-dependent ablations are re-run under the main setting.

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|---|
| Full SA-MCGS (locked main) | 40 | 0.000 | 0.875 | 1.000 | 0.800 | 0.504 | 6.225 | 0.000 | 0.000 | 0.000 |
| No relation-first memory | 40 | 0.000 | 0.900 | 1.000 | 0.900 | 0.510 | 6.250 | 0.025 | 0.000 | 0.100 |
| No critical-pair ledger/revisit | 40 | 0.000 | 0.825 | 0.950 | 0.725 | 0.675 | 4.125 | -0.050 | -0.050 | -0.075 |
| Random local-window selection | 40 | 0.000 | 0.925 | 1.000 | 0.725 | 0.510 | 6.250 | 0.050 | 0.000 | -0.075 |
