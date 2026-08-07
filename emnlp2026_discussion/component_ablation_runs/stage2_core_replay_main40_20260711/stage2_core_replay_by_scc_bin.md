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
