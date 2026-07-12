# Stage 1 Component Ablation: 40-Case Combined View

This report combines the original 20 matched cases with 20 additional long-cycle stress configurations. Full SA-MCGS rows are copied from locked main results; LLM-dependent ablations are re-run under the same budget/window setting.

## main20

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full SA-MCGS (locked main) | 20 | 0.000 | 0.900 | 1.000 | 0.750 | 0.513 | 8.100 | 0.000 | 0.000 | 0.000 |
| No relation-first memory | 20 | 0.000 | 0.850 | 1.000 | 0.750 | 0.520 | 7.850 | -0.050 | 0.000 | 0.000 |
| No critical-pair ledger/revisit | 20 | 0.000 | 0.900 | 0.950 | 0.500 | 0.724 | 4.150 | 0.000 | -0.050 | -0.250 |
| Random local-window selection | 20 | 0.000 | 0.850 | 0.950 | 0.650 | 0.520 | 7.850 | -0.050 | -0.050 | -0.100 |

## extra_long20

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full SA-MCGS (locked main) | 20 | 0.000 | 0.800 | 1.000 | 0.650 | 0.530 | 11.850 | 0.000 | 0.000 | 0.000 |
| No relation-first memory | 20 | 0.000 | 0.900 | 0.950 | 0.650 | 0.532 | 11.500 | 0.100 | -0.050 | 0.000 |
| No critical-pair ledger/revisit | 20 | 0.000 | 0.800 | 0.700 | 0.200 | 0.806 | 4.400 | 0.000 | -0.300 | -0.450 |
| Random local-window selection | 20 | 0.000 | 0.900 | 0.900 | 0.450 | 0.532 | 11.500 | 0.100 | -0.100 | -0.200 |

## combined40

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full SA-MCGS (locked main) | 40 | 0.000 | 0.850 | 1.000 | 0.700 | 0.521 | 9.975 | 0.000 | 0.000 | 0.000 |
| No relation-first memory | 40 | 0.000 | 0.875 | 0.975 | 0.700 | 0.526 | 9.675 | 0.025 | -0.025 | 0.000 |
| No critical-pair ledger/revisit | 40 | 0.000 | 0.850 | 0.825 | 0.350 | 0.765 | 4.275 | 0.000 | -0.175 | -0.350 |
| Random local-window selection | 40 | 0.000 | 0.875 | 0.925 | 0.550 | 0.526 | 9.675 | 0.025 | -0.075 | -0.150 |

## Short Interpretation

- The additional long-cycle subset is harder for Full SA-MCGS than the original main20 subset, especially on Risk-all. This is expected because the added cases concentrate on larger SCCs and non-direct-mutex templates.

- Removing the persistent critical-pair ledger/revisit mechanism produces the largest and most consistent degradation, especially in Risk-any/Risk-all, and strongly increases compression by shrinking the core too aggressively.

- Random local-window selection also reduces endpoint completeness, supporting the value of graph-guided/local-window search policy beyond repeated local prompting.

- Removing relation-first memory has a milder aggregate effect in this sample; its effect should be described cautiously, mainly as part of the component-level diagnostic rather than as a uniformly dominant module.

