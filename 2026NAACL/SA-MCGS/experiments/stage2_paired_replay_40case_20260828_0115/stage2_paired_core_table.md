# Stage 2 Paired Dynamic-vs-Locked Core Replay

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Avg cumulative evictions | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full recompute/replacement (paired replay) | 40 | 40 | 0 | 0.850 | 1.000 | 0.700 | 0.850 | 0.521 | 9.975 | 24.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 40 | 40 | 0 | 0.850 | 0.875 | 0.425 | 0.650 | 0.521 | 9.975 | 0.000 | 0.000 | -0.125 | -0.275 | 0.000 | 0.000 |
