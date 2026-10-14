# Stage 2 Paired Dynamic-vs-Locked Core Replay

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Avg cumulative evictions | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full recompute/replacement (paired replay) | 1 | 1 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 0.529 | 16.000 | 46.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 1 | 1 | 0 | 1.000 | 1.000 | 0.000 | 0.500 | 0.529 | 16.000 | 0.000 | 0.000 | 0.000 | -1.000 | 0.000 | 0.000 |
