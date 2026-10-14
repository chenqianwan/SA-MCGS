# Stage 2 Paired Dynamic-vs-Locked Core Replay Report

Both policies are derived from the same frozen Full trace. No LLM is called.
Every valid case passed original-main-row identity/trace validation and final Full parity.
Both policies consume the same selector proposal at every prefix. The locked policy
changes only admission/eviction: OC signals, relation seeding, critical-pair
protection, pair closure, scoring thresholds, and cap remain in the shared selector.
Root@3 is inherited from the shared frozen search trajectory and is therefore not a
core-policy effect.
Cases sharing physical_scc_uid are dependent injection conditions. Aggregate means
are descriptive only; this report does not apply naive i.i.d. significance tests.

The legacy Stage-1 summary is diagnostic only. The deprecated rebuttal
`monotone-core` result and its -25 point claim are not reused.

# Stage 2 Paired Dynamic-vs-Locked Core Replay

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Avg cumulative evictions | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full recompute/replacement (paired replay) | 40 | 40 | 0 | 0.850 | 1.000 | 0.700 | 0.850 | 0.521 | 9.975 | 24.250 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 40 | 40 | 0 | 0.850 | 0.875 | 0.425 | 0.650 | 0.521 | 9.975 | 0.000 | 0.000 | -0.125 | -0.275 | 0.000 | 0.000 |


# Stage 2 Paired Dynamic-vs-Locked Core Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Avg cumulative evictions | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|
| large (20-34) | Full recompute/replacement (paired replay) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 12.167 | 31.083 | 0.000 |
| large (20-34) | Locked no-replacement (paired replay) | 24 | 0.792 | 0.917 | 0.458 | 0.533 | 12.167 | 0.000 | -0.125 |
| medium (12-18) | Full recompute/replacement (paired replay) | 10 | 0.900 | 1.000 | 0.900 | 0.503 | 7.700 | 17.200 | 0.000 |
| medium (12-18) | Locked no-replacement (paired replay) | 10 | 0.900 | 0.800 | 0.200 | 0.503 | 7.700 | 0.000 | -0.700 |
| small (9-11) | Full recompute/replacement (paired replay) | 6 | 1.000 | 1.000 | 0.833 | 0.504 | 5.000 | 8.667 | 0.000 |
| small (9-11) | Locked no-replacement (paired replay) | 6 | 1.000 | 0.833 | 0.667 | 0.504 | 5.000 | 0.000 | -0.167 |
