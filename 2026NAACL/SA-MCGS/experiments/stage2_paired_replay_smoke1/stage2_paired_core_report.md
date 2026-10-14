# Stage 2 Paired Dynamic-vs-Locked Core Replay Report

Both policies are derived from the same frozen Full trace. No LLM is called.
Every valid case passed original-main-row identity/trace validation and final Full parity.
Both policies consume the same selector proposal at every prefix. The locked policy
changes only admission/eviction: OC signals, relation seeding, critical-pair
protection, pair closure, scoring thresholds, and cap remain in the shared selector.
Root@3 is inherited from the shared frozen search trajectory and is therefore not a
core-policy effect.

The legacy Stage-1 summary is diagnostic only. The deprecated rebuttal
`monotone-core` result and its -25 point claim are not reused.

# Stage 2 Paired Dynamic-vs-Locked Core Replay

| Variant | Attempted | Valid | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Avg cumulative evictions | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full recompute/replacement (paired replay) | 1 | 1 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 0.529 | 16.000 | 46.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 1 | 1 | 0 | 1.000 | 1.000 | 0.000 | 0.500 | 0.529 | 16.000 | 0.000 | 0.000 | 0.000 | -1.000 | 0.000 | 0.000 |


# Stage 2 Paired Dynamic-vs-Locked Core Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Avg cumulative evictions | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|
| large (20-34) | Full recompute/replacement (paired replay) | 1 | 1.000 | 1.000 | 1.000 | 0.529 | 16.000 | 46.000 | 0.000 |
| large (20-34) | Locked no-replacement (paired replay) | 1 | 1.000 | 1.000 | 0.000 | 0.529 | 16.000 | 0.000 | -1.000 |
