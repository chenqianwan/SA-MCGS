# Stage 1 Component Ablation Main Table

Main run: 20 matched cases. Full SA-MCGS rows are copied from locked main results; LLM-dependent ablations are re-run under the main setting.

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|---|
| Full SA-MCGS (locked main) | 20 | 0.000 | 0.900 | 1.000 | 0.750 | 0.513 | 8.100 | 0.000 | 0.000 | 0.000 |
| No relation-first memory | 20 | 0.000 | 0.850 | 1.000 | 0.750 | 0.520 | 7.850 | -0.050 | 0.000 | 0.000 |
| No critical-pair ledger/revisit | 20 | 0.000 | 0.900 | 0.950 | 0.500 | 0.724 | 4.150 | 0.000 | -0.050 | -0.250 |
| Random local-window selection | 20 | 0.000 | 0.850 | 0.950 | 0.650 | 0.520 | 7.850 | -0.050 | -0.050 | -0.100 |
