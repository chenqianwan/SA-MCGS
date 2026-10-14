# Stage 2 Paired Dynamic-vs-Locked Core Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Avg cumulative evictions | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|
| large (20-34) | Full recompute/replacement (paired replay) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 12.167 | 31.083 | 0.000 |
| large (20-34) | Locked no-replacement (paired replay) | 24 | 0.792 | 0.917 | 0.458 | 0.533 | 12.167 | 0.000 | -0.125 |
| medium (12-18) | Full recompute/replacement (paired replay) | 32 | 0.875 | 1.000 | 0.875 | 0.504 | 7.375 | 16.844 | 0.000 |
| medium (12-18) | Locked no-replacement (paired replay) | 32 | 0.875 | 0.844 | 0.281 | 0.504 | 7.375 | 0.000 | -0.594 |
| small (9-11) | Full recompute/replacement (paired replay) | 24 | 0.917 | 1.000 | 0.750 | 0.504 | 5.000 | 9.792 | 0.000 |
| small (9-11) | Locked no-replacement (paired replay) | 24 | 0.917 | 0.833 | 0.417 | 0.504 | 5.000 | 0.000 | -0.333 |
