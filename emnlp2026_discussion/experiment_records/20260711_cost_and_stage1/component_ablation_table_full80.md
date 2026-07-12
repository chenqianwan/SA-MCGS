# Component Ablation Table: Full 80 gpt-4o Configurations

| Variant | N | Invalid | Root@3 | Risk-any | Risk-all | Compression | Avg core size | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression | Delta Avg core size | Avg LLM calls | Avg tokens | Avg runtime sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full SA-MCGS (locked main) | 80 | 0.000 | 0.863 | 1.000 | 0.750 | 0.513 | 8.100 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |  |  | 244.320 |
| No relation-first memory | 80 | 0.000 | 0.887 | 0.988 | 0.800 | 0.518 | 7.963 | 0.025 | -0.012 | 0.050 | 0.005 | -0.137 | 58.562 | 193380.163 | 184.812 |
| No critical-pair ledger/revisit | 80 | 0.000 | 0.838 | 0.887 | 0.537 | 0.720 | 4.200 | -0.025 | -0.113 | -0.213 | 0.208 | -3.900 | 58.200 | 194265.525 | 194.824 |
| Random local-window selection | 80 | 0.000 | 0.900 | 0.963 | 0.637 | 0.518 | 7.963 | 0.037 | -0.037 | -0.113 | 0.005 | -0.137 | 58.163 | 188036.600 | 178.134 |
