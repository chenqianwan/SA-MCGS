# Compact Component Ablation by SCC Size Bin

| SCC bin | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| small (9-11) | Full SA-MCGS (locked main) | 24 | 0.917 | 1.000 | 0.750 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| small (9-11) | No relation-first memory | 24 | 0.917 | 1.000 | 0.833 | 0.517 | 0.000 | 0.000 | 0.083 | 0.013 |
| small (9-11) | No critical-pair ledger/revisit | 24 | 0.833 | 0.917 | 0.625 | 0.656 | -0.083 | -0.083 | -0.125 | 0.152 |
| small (9-11) | Random local-window selection | 24 | 0.958 | 1.000 | 0.708 | 0.517 | 0.042 | 0.000 | -0.042 | 0.013 |
| medium (12-18) | Full SA-MCGS (locked main) | 32 | 0.875 | 1.000 | 0.875 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| medium (12-18) | No relation-first memory | 32 | 0.906 | 1.000 | 0.938 | 0.508 | 0.031 | 0.000 | 0.062 | 0.004 |
| medium (12-18) | No critical-pair ledger/revisit | 32 | 0.875 | 1.000 | 0.750 | 0.696 | 0.000 | 0.000 | -0.125 | 0.192 |
| medium (12-18) | Random local-window selection | 32 | 0.906 | 0.969 | 0.719 | 0.508 | 0.031 | -0.031 | -0.156 | 0.004 |
| large (20-34) | Full SA-MCGS (locked main) | 24 | 0.792 | 1.000 | 0.583 | 0.533 | 0.000 | 0.000 | 0.000 | 0.000 |
| large (20-34) | No relation-first memory | 24 | 0.833 | 0.958 | 0.583 | 0.533 | 0.042 | -0.042 | 0.000 | 0.000 |
| large (20-34) | No critical-pair ledger/revisit | 24 | 0.792 | 0.708 | 0.167 | 0.816 | 0.000 | -0.292 | -0.417 | 0.284 |
| large (20-34) | Random local-window selection | 24 | 0.833 | 0.917 | 0.458 | 0.533 | 0.042 | -0.083 | -0.125 | 0.000 |
