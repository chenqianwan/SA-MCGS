# Stage 2 Paired Dynamic-vs-Locked Core Replay

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Avg cumulative evictions | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full recompute/replacement (paired replay) | 80 | 80 | 0 | 0.863 | 1.000 | 0.750 | 0.875 | 0.513 | 8.100 | 19.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 80 | 80 | 0 | 0.863 | 0.863 | 0.375 | 0.619 | 0.513 | 8.100 | 0.000 | 0.000 | -0.137 | -0.375 | 0.000 | 0.000 |
