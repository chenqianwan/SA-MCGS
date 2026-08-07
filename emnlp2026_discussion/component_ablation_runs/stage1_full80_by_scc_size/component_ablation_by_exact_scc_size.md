# Component Ablation by Exact SCC Size

| SCC size | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 | Full SA-MCGS (locked main) | 8 | 0.875 | 1.000 | 0.875 | 0.444 | 0.000 | 0.000 | 0.000 | 0.000 |
| 9 | No relation-first memory | 8 | 1.000 | 1.000 | 0.875 | 0.477 | 0.125 | 0.000 | 0.000 | 0.032 |
| 9 | No critical-pair ledger/revisit | 8 | 0.750 | 0.875 | 0.500 | 0.631 | -0.125 | -0.125 | -0.375 | 0.187 |
| 9 | Random local-window selection | 8 | 1.000 | 1.000 | 0.875 | 0.477 | 0.125 | 0.000 | 0.000 | 0.032 |
| 10 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 0.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 10 | No relation-first memory | 4 | 1.000 | 1.000 | 0.750 | 0.545 | 0.000 | 0.000 | 0.750 | 0.045 |
| 10 | No critical-pair ledger/revisit | 4 | 1.000 | 1.000 | 1.000 | 0.682 | 0.000 | 0.000 | 1.000 | 0.182 |
| 10 | Random local-window selection | 4 | 1.000 | 1.000 | 0.250 | 0.545 | 0.000 | 0.000 | 0.250 | 0.045 |
| 11 | Full SA-MCGS (locked main) | 12 | 0.917 | 1.000 | 0.917 | 0.545 | 0.000 | 0.000 | 0.000 | 0.000 |
| 11 | No relation-first memory | 12 | 0.833 | 1.000 | 0.833 | 0.534 | -0.083 | 0.000 | -0.083 | -0.011 |
| 11 | No critical-pair ledger/revisit | 12 | 0.833 | 0.917 | 0.583 | 0.664 | -0.083 | -0.083 | -0.333 | 0.119 |
| 11 | Random local-window selection | 12 | 0.917 | 1.000 | 0.750 | 0.534 | 0.000 | 0.000 | -0.167 | -0.011 |
| 12 | Full SA-MCGS (locked main) | 12 | 1.000 | 1.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 12 | No relation-first memory | 12 | 1.000 | 1.000 | 0.917 | 0.508 | 0.000 | 0.000 | -0.083 | 0.008 |
| 12 | No critical-pair ledger/revisit | 12 | 1.000 | 1.000 | 0.833 | 0.732 | 0.000 | 0.000 | -0.167 | 0.232 |
| 12 | Random local-window selection | 12 | 1.000 | 1.000 | 0.833 | 0.508 | 0.000 | 0.000 | -0.167 | 0.008 |
| 14 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 0.500 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 14 | No relation-first memory | 4 | 1.000 | 1.000 | 0.750 | 0.500 | 0.000 | 0.000 | 0.250 | 0.000 |
| 14 | No critical-pair ledger/revisit | 4 | 1.000 | 1.000 | 1.000 | 0.696 | 0.000 | 0.000 | 0.500 | 0.196 |
| 14 | Random local-window selection | 4 | 1.000 | 1.000 | 0.750 | 0.500 | 0.000 | 0.000 | 0.250 | 0.000 |
| 16 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 16 | No relation-first memory | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 16 | No critical-pair ledger/revisit | 4 | 1.000 | 1.000 | 1.000 | 0.703 | 0.000 | 0.000 | 0.000 | 0.203 |
| 16 | Random local-window selection | 4 | 1.000 | 1.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 17 | Full SA-MCGS (locked main) | 4 | 0.000 | 1.000 | 0.500 | 0.529 | 0.000 | 0.000 | 0.000 | 0.000 |
| 17 | No relation-first memory | 4 | 0.250 | 1.000 | 1.000 | 0.529 | 0.250 | 0.000 | 0.500 | 0.000 |
| 17 | No critical-pair ledger/revisit | 4 | 0.000 | 1.000 | 0.000 | 0.647 | 0.000 | 0.000 | -0.500 | 0.118 |
| 17 | Random local-window selection | 4 | 0.250 | 0.750 | 0.250 | 0.529 | 0.250 | -0.250 | -0.250 | 0.000 |
| 18 | Full SA-MCGS (locked main) | 8 | 1.000 | 1.000 | 1.000 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |
| 18 | No relation-first memory | 8 | 1.000 | 1.000 | 1.000 | 0.506 | 0.000 | 0.000 | 0.000 | 0.006 |
| 18 | No critical-pair ledger/revisit | 8 | 1.000 | 1.000 | 0.750 | 0.662 | 0.000 | 0.000 | -0.250 | 0.162 |
| 18 | Random local-window selection | 8 | 1.000 | 1.000 | 0.625 | 0.506 | 0.000 | 0.000 | -0.375 | 0.006 |
| 20 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 0.500 | 0.550 | 0.000 | 0.000 | 0.000 | 0.000 |
| 20 | No relation-first memory | 4 | 0.500 | 1.000 | 0.750 | 0.550 | -0.500 | 0.000 | 0.250 | 0.000 |
| 20 | No critical-pair ledger/revisit | 4 | 0.750 | 0.750 | 0.000 | 0.762 | -0.250 | -0.250 | -0.500 | 0.212 |
| 20 | Random local-window selection | 4 | 1.000 | 0.750 | 0.250 | 0.550 | 0.000 | -0.250 | -0.250 | 0.000 |
| 24 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 0.750 | 0.542 | 0.000 | 0.000 | 0.000 | 0.000 |
| 24 | No relation-first memory | 4 | 0.750 | 0.750 | 0.000 | 0.542 | -0.250 | -0.250 | -0.750 | 0.000 |
| 24 | No critical-pair ledger/revisit | 4 | 0.750 | 1.000 | 0.000 | 0.854 | -0.250 | 0.000 | -0.750 | 0.312 |
| 24 | Random local-window selection | 4 | 0.750 | 1.000 | 0.000 | 0.542 | -0.250 | 0.000 | -0.750 | 0.000 |
| 25 | Full SA-MCGS (locked main) | 8 | 0.750 | 1.000 | 0.500 | 0.520 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | No relation-first memory | 8 | 1.000 | 1.000 | 0.625 | 0.520 | 0.250 | 0.000 | 0.125 | 0.000 |
| 25 | No critical-pair ledger/revisit | 8 | 0.875 | 0.750 | 0.375 | 0.790 | 0.125 | -0.250 | -0.125 | 0.270 |
| 25 | Random local-window selection | 8 | 0.875 | 1.000 | 0.625 | 0.520 | 0.125 | 0.000 | 0.125 | 0.000 |
| 28 | Full SA-MCGS (locked main) | 4 | 0.250 | 1.000 | 0.250 | 0.536 | 0.000 | 0.000 | 0.000 | 0.000 |
| 28 | No relation-first memory | 4 | 0.750 | 1.000 | 0.750 | 0.536 | 0.500 | 0.000 | 0.500 | 0.000 |
| 28 | No critical-pair ledger/revisit | 4 | 0.500 | 0.750 | 0.250 | 0.812 | 0.250 | -0.250 | 0.000 | 0.277 |
| 28 | Random local-window selection | 4 | 0.500 | 1.000 | 0.750 | 0.536 | 0.250 | 0.000 | 0.500 | 0.000 |
| 34 | Full SA-MCGS (locked main) | 4 | 1.000 | 1.000 | 1.000 | 0.529 | 0.000 | 0.000 | 0.000 | 0.000 |
| 34 | No relation-first memory | 4 | 1.000 | 1.000 | 0.750 | 0.529 | 0.000 | 0.000 | -0.250 | 0.000 |
| 34 | No critical-pair ledger/revisit | 4 | 1.000 | 0.250 | 0.000 | 0.890 | 0.000 | -0.750 | -1.000 | 0.360 |
| 34 | Random local-window selection | 4 | 1.000 | 0.750 | 0.500 | 0.529 | 0.000 | -0.250 | -0.500 | 0.000 |
