# Stage 2 Paired Dynamic-vs-Locked Core Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Avg cumulative evictions | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|
| large (20-34) | Full recompute/replacement (paired replay) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 12.167 | 31.083 | 0.000 |
| large (20-34) | Locked no-replacement (paired replay) | 24 | 0.792 | 0.917 | 0.458 | 0.533 | 12.167 | 0.000 | -0.125 |
| medium (12-18) | Full recompute/replacement (paired replay) | 10 | 0.900 | 1.000 | 0.900 | 0.503 | 7.700 | 17.200 | 0.000 |
| medium (12-18) | Locked no-replacement (paired replay) | 10 | 0.900 | 0.800 | 0.200 | 0.503 | 7.700 | 0.000 | -0.700 |
| small (9-11) | Full recompute/replacement (paired replay) | 6 | 1.000 | 1.000 | 0.833 | 0.504 | 5.000 | 8.667 | 0.000 |
| small (9-11) | Locked no-replacement (paired replay) | 6 | 1.000 | 0.833 | 0.667 | 0.504 | 5.000 | 0.000 | -0.167 |
