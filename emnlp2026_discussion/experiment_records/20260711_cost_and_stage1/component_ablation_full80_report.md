# Stage 1 Component Ablation: Full 80 and SCC-Size Analysis

Scope: all 80 gpt-4o case configurations from the locked main experiment. Full SA-MCGS rows are copied from locked main results; three LLM-dependent ablations are re-run under B=60, window=4, case concurrency=4, internal concurrency=4. SCC-size bins are assigned from the matched Full/plan case metadata, not from per-variant payload fields.

## Full 80 Summary

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size | Avg LLM calls | Avg tokens | Avg runtime sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full SA-MCGS (locked main) | 80 | 0.000 | 0.863 | 1.000 | 0.750 | 0.513 | 8.100 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |  |  | 244.320 |
| No relation-first memory | 80 | 0.000 | 0.887 | 0.988 | 0.800 | 0.518 | 7.963 | 0.025 | -0.012 | 0.050 | 0.005 | -0.137 | 58.562 | 193380.163 | 184.812 |
| No critical-pair ledger/revisit | 80 | 0.000 | 0.838 | 0.887 | 0.537 | 0.720 | 4.200 | -0.025 | -0.113 | -0.213 | 0.208 | -3.900 | 58.200 | 194265.525 | 194.824 |
| Random local-window selection | 80 | 0.000 | 0.900 | 0.963 | 0.637 | 0.518 | 7.963 | 0.037 | -0.037 | -0.113 | 0.005 | -0.137 | 58.163 | 188036.600 | 178.134 |

## SCC Size Bin Summary

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| small (9-11) | Full SA-MCGS (locked main) | 24 | 0.917 | 1.000 | 0.750 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| small (9-11) | No relation-first memory | 24 | 0.917 | 1.000 | 0.833 | 0.517 | 0.000 | 0.000 | 0.083 | 0.013 |
| small (9-11) | No critical-pair ledger/revisit | 24 | 0.833 | 0.917 | 0.625 | 0.656 | -0.083 | -0.083 | -0.125 | 0.152 |
| small (9-11) | Random local-window selection | 24 | 0.958 | 1.000 | 0.708 | 0.517 | 0.042 | 0.000 | -0.042 | 0.013 |
| medium (12-18) | Full SA-MCGS (locked main) | 32 | 0.875 | 1.000 | 0.875 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| medium (12-18) | No relation-first memory | 32 | 0.906 | 1.000 | 0.938 | 0.508 | 0.031 | 0.000 | 0.062 | 0.004 |
| medium (12-18) | No critical-pair ledger/revisit | 32 | 0.875 | 1.000 | 0.750 | 0.696 | 0.000 | 0.000 | -0.125 | 0.192 |
| medium (12-18) | Random local-window selection | 32 | 0.906 | 0.969 | 0.719 | 0.508 | 0.031 | -0.031 | -0.156 | 0.004 |
| large (20-34) | Full SA-MCGS (locked main) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 0.000 | 0.000 | 0.000 | 0.000 |
| large (20-34) | No relation-first memory | 24 | 0.833 | 0.958 | 0.583 | 0.533 | 0.042 | -0.042 | 0.000 | 0.000 |
| large (20-34) | No critical-pair ledger/revisit | 24 | 0.792 | 0.708 | 0.167 | 0.816 | 0.000 | -0.292 | -0.417 | 0.284 |
| large (20-34) | Random local-window selection | 24 | 0.833 | 0.917 | 0.458 | 0.533 | 0.042 | -0.083 | -0.125 | 0.000 |

## Notes

- Large SCCs show the clearest endpoint-retention degradation when the critical-pair ledger/revisit mechanism is removed.

- In small and medium SCCs, removing the critical-pair ledger/revisit still changes output structure substantially: compression increases and average core size drops, even when aggregate endpoint metrics degrade more mildly.

- Random local-window selection mainly affects Risk-all, supporting graph-guided window selection beyond repeated local prompting.

- The no-relation-first-memory variant is not uniformly worse in this gpt-4o sample; it should be described cautiously as a diagnostic component rather than a dominant standalone contributor.

