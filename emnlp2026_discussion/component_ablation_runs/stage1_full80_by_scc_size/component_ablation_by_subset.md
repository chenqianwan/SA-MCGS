# Component Ablation by Run Subset

| Subset | Variant | N | Root@3 | Risk-any | Risk-all | Compression | Delta Root@3 | Delta Risk-any | Delta Risk-all | Delta Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| main20 | Full SA-MCGS (locked main) | 20 | 0.900 | 1.000 | 0.750 | 0.513 | 0.000 | 0.000 | 0.000 | 0.000 |
| main20 | No relation-first memory | 20 | 0.850 | 1.000 | 0.750 | 0.520 | -0.050 | 0.000 | 0.000 | 0.007 |
| main20 | No critical-pair ledger/revisit | 20 | 0.900 | 0.950 | 0.500 | 0.724 | 0.000 | -0.050 | -0.250 | 0.211 |
| main20 | Random local-window selection | 20 | 0.850 | 0.950 | 0.650 | 0.520 | -0.050 | -0.050 | -0.100 | 0.007 |
| long20 | Full SA-MCGS (locked main) | 20 | 0.800 | 1.000 | 0.650 | 0.530 | 0.000 | 0.000 | 0.000 | 0.000 |
| long20 | No relation-first memory | 20 | 0.900 | 0.950 | 0.650 | 0.532 | 0.100 | -0.050 | 0.000 | 0.002 |
| long20 | No critical-pair ledger/revisit | 20 | 0.800 | 0.700 | 0.200 | 0.806 | 0.000 | -0.300 | -0.450 | 0.277 |
| long20 | Random local-window selection | 20 | 0.900 | 0.900 | 0.450 | 0.532 | 0.100 | -0.100 | -0.200 | 0.002 |
| midshort40 | Full SA-MCGS (locked main) | 40 | 0.875 | 1.000 | 0.800 | 0.504 | 0.000 | 0.000 | 0.000 | 0.000 |
| midshort40 | No relation-first memory | 40 | 0.900 | 1.000 | 0.900 | 0.510 | 0.025 | 0.000 | 0.100 | 0.006 |
| midshort40 | No critical-pair ledger/revisit | 40 | 0.825 | 0.950 | 0.725 | 0.675 | -0.050 | -0.050 | -0.075 | 0.171 |
| midshort40 | Random local-window selection | 40 | 0.925 | 1.000 | 0.725 | 0.510 | 0.050 | 0.000 | -0.075 | 0.006 |
