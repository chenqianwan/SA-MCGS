# Merged Cost, Reliability, and Performance Table

Cost columns are averaged over all attempted cases, including invalid outputs. Performance columns are averaged over valid outputs only. Runtime is end-to-end method runtime when available; for invalid outputs it is recovered from audit timestamps.

| Method | Scale | Cases | Valid | Invalid | Invalid rate | API calls / case | Input tok. / case | Output tok. / case | Total tok. / case | Runtime / case | Root@3 | Risk-any | Risk-all | Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full-SCC Naive (single attempt) | Overall | 20 | 17 | 3 | 0.150 | 1.00 | 20,429 | 3,182 | 23,611 | 20.4s | 0.412 | 0.765 | 0.471 | 0.693 |
| Full-SCC Naive (single attempt) | large | 5 | 2 | 3 | 0.600 | 1.00 | 39,483 | 4,225 | 43,708 | 28.7s | 0.000 | 1.000 | 0.000 | 0.811 |
| Full-SCC Naive (single attempt) | medium | 7 | 7 | 0 | 0.000 | 1.00 | 25,025 | 3,606 | 28,631 | 20.5s | 0.000 | 0.571 | 0.143 | 0.760 |
| Full-SCC Naive (single attempt) | small | 8 | 8 | 0 | 0.000 | 1.00 | 4,499 | 2,159 | 6,658 | 15.0s | 0.875 | 0.875 | 0.875 | 0.604 |
| GraphRAG-style LEA | Overall | 20 | 20 | 0 | 0.000 | 17.35 | 35,726 | 22,721 | 58,447 | 175.6s | 0.750 | 0.900 | 0.400 | 0.515 |
| GraphRAG-style LEA | large | 5 | 5 | 0 | 0.000 | 28.20 | 65,812 | 41,454 | 107,266 | 319.9s | 0.600 | 1.000 | 0.400 | 0.529 |
| GraphRAG-style LEA | medium | 7 | 7 | 0 | 0.000 | 17.71 | 36,966 | 25,405 | 62,370 | 183.3s | 0.714 | 1.000 | 0.286 | 0.511 |
| GraphRAG-style LEA | small | 8 | 8 | 0 | 0.000 | 10.25 | 15,837 | 8,666 | 24,503 | 78.7s | 0.875 | 0.750 | 0.500 | 0.509 |
| SA-MCGS | Overall | 20 | 20 | 0 | 0.000 | 50.45 | 99,108 | 62,057 | 161,166 | 524.6s | 0.850 | 0.850 | 0.750 | 0.515 |
| SA-MCGS | large | 5 | 5 | 0 | 0.000 | 50.80 | 118,736 | 73,895 | 192,631 | 671.3s | 0.600 | 0.400 | 0.400 | 0.529 |
| SA-MCGS | medium | 7 | 7 | 0 | 0.000 | 52.71 | 110,714 | 75,699 | 186,413 | 576.8s | 0.857 | 1.000 | 0.714 | 0.511 |
| SA-MCGS | small | 8 | 8 | 0 | 0.000 | 48.25 | 76,686 | 42,722 | 119,408 | 387.3s | 1.000 | 1.000 | 1.000 | 0.509 |
