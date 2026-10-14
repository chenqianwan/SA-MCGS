# Stage 2 Paired Dynamic-vs-Locked Core Replay Report

Both policies are derived from the same frozen Full trace. No LLM is called.
Every valid case passed original-main-row identity/trace validation and final
Full parity.
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
| Full recompute/replacement (paired replay) | 80 | 80 | 0 | 0.863 | 1.000 | 0.750 | 0.875 | 0.513 | 8.100 | 19.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Locked no-replacement (paired replay) | 80 | 80 | 0 | 0.863 | 0.863 | 0.375 | 0.619 | 0.513 | 8.100 | 0.000 | 0.000 | -0.137 | -0.375 | 0.000 | 0.000 |


# Stage 2 Paired Dynamic-vs-Locked Core Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Avg cumulative evictions | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|
| large (20-34) | Full recompute/replacement (paired replay) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 12.167 | 31.083 | 0.000 |
| large (20-34) | Locked no-replacement (paired replay) | 24 | 0.792 | 0.917 | 0.458 | 0.533 | 12.167 | 0.000 | -0.125 |
| medium (12-18) | Full recompute/replacement (paired replay) | 32 | 0.875 | 1.000 | 0.875 | 0.504 | 7.375 | 16.844 | 0.000 |
| medium (12-18) | Locked no-replacement (paired replay) | 32 | 0.875 | 0.844 | 0.281 | 0.504 | 7.375 | 0.000 | -0.594 |
| small (9-11) | Full recompute/replacement (paired replay) | 24 | 0.917 | 1.000 | 0.750 | 0.504 | 5.000 | 9.792 | 0.000 |
| small (9-11) | Locked no-replacement (paired replay) | 24 | 0.917 | 0.833 | 0.417 | 0.504 | 5.000 | 0.000 | -0.333 |

## Source-SCC clustered inference

The 80 cases come from 20 physical source SCCs with four injected variants per
SCC.  A 20,000-replicate source-SCC clustered bootstrap gives a paired
Full-minus-Locked Risk-all difference of **+37.5 percentage points** (95%
percentile interval **[+12.5, +60.0]**), Risk-any **+13.8 points**
(**[+5.0, +22.5]**), and risk coverage **+25.6 points**
(**[+11.2, +38.8]**).  Full details and the fail-closed offline recomputation
are in `stage2_clustered_paired_inference.md` and
`clustered_paired_inference.py`.
