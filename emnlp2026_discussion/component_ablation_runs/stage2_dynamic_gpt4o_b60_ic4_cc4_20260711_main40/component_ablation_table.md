# Stage 2 Dynamic Component Ablation Table

Dynamic run: matched cases with full rollout trajectories re-run. Full SA-MCGS rows are copied from locked main results; Stage 2 variants disable OC/core signals or alter final-core construction while preserving the main local evidence schema and rollout budget.

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
|---|---|---|---|---|---|---|---|---|---|---|
| Full SA-MCGS (locked main) | 40 | 0.000 | 0.850 | 1.000 | 0.700 | 0.521 | 9.975 | 0.000 | 0.000 | 0.000 |
| No OC/core signal | 40 | 0.000 | 0.850 | 1.000 | 0.600 | 0.522 | 9.725 | 0.000 | 0.000 | -0.100 |
| Monotone core | 40 | 0.000 | 0.775 | 0.875 | 0.450 | 0.761 | 4.750 | -0.075 | -0.125 | -0.250 |
| No pair closure in final core | 40 | 0.000 | 0.800 | 0.950 | 0.675 | 0.530 | 9.450 | -0.050 | -0.050 | -0.025 |
