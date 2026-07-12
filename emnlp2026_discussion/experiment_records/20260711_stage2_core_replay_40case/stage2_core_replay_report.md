# Stage 2 Core-Only Replay Report

Scope: 40 matched Full SA-MCGS cases replayed without new LLM calls.

Variants:
- No OC/core signal: remove the OC signal from evidence scoring and final-core priority/keep rules.
- Monotone core: score-ordered accumulation without protected pair seeding or final pair closure.
- No pair closure in final core: keep dynamic priority/protected seeding but disable the final counterpart-closure step.

## Main Table

# Stage 2 Core-Only Replay: 40 Cases

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full SA-MCGS (locked main) | 40 | 0.000 | 0.850 | 1.000 | 0.700 | 0.850 | 0.521 | 9.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| No OC/core signal (replay) | 40 | 0.000 | 0.850 | 1.000 | 0.700 | 0.850 | 0.521 | 9.975 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Monotone core (replay) | 40 | 0.000 | 0.850 | 0.975 | 0.600 | 0.787 | 0.771 | 4.800 | 0.000 | -0.025 | -0.100 | 0.250 | -5.175 |
| No pair closure in final core (replay) | 40 | 0.000 | 0.850 | 1.000 | 0.675 | 0.838 | 0.523 | 9.900 | 0.000 | 0.000 | -0.025 | 0.002 | -0.075 |


## SCC Bin Table

# Stage 2 Core-Only Replay by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Risk coverage | Compression | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression |
|---|---|---|---|---|---|---|---|---|---|---|---|
| small (9-11) | Full SA-MCGS (locked main) | 6 | 1.000 | 1.000 | 0.833 | 0.917 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| small (9-11) | No OC/core signal (replay) | 6 | 1.000 | 1.000 | 0.833 | 0.917 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| small (9-11) | Monotone core (replay) | 6 | 1.000 | 1.000 | 0.667 | 0.833 | 0.768 | 0.000 | 0.000 | -0.167 | 0.264 |
| small (9-11) | No pair closure in final core (replay) | 6 | 1.000 | 1.000 | 0.833 | 0.917 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| medium (12-18) | Full SA-MCGS (locked main) | 10 | 0.900 | 1.000 | 0.900 | 0.950 | 0.503 | 0.000 | 0.000 | 0.000 | 0.000 |
| medium (12-18) | No OC/core signal (replay) | 10 | 0.900 | 1.000 | 0.900 | 0.950 | 0.503 | 0.000 | 0.000 | 0.000 | 0.000 |
| medium (12-18) | Monotone core (replay) | 10 | 0.900 | 1.000 | 0.700 | 0.850 | 0.774 | 0.000 | 0.000 | -0.200 | 0.271 |
| medium (12-18) | No pair closure in final core (replay) | 10 | 0.900 | 1.000 | 0.900 | 0.950 | 0.503 | 0.000 | 0.000 | 0.000 | 0.000 |
| large (20-34) | Full SA-MCGS (locked main) | 24 | 0.792 | 1.000 | 0.583 | 0.792 | 0.533 | 0.000 | 0.000 | 0.000 | 0.000 |
| large (20-34) | No OC/core signal (replay) | 24 | 0.792 | 1.000 | 0.583 | 0.792 | 0.533 | 0.000 | 0.000 | 0.000 | 0.000 |
| large (20-34) | Monotone core (replay) | 24 | 0.792 | 0.958 | 0.542 | 0.750 | 0.771 | 0.000 | -0.042 | -0.042 | 0.238 |
| large (20-34) | No pair closure in final core (replay) | 24 | 0.792 | 1.000 | 0.542 | 0.771 | 0.536 | 0.000 | 0.000 | -0.042 | 0.004 |
