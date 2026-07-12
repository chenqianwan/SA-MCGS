| Method | Scale | Cases | Case conc. | Internal conc. | Calls / case | Input tok. / case | Output tok. / case | Total tok. / case | Runtime / case | Invalid output | Root@3 | Risk-any | Risk-all | Compression |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Full-SCC Naive, single attempt | Overall | 25 | 1 | 1 | 1.000 | 15923 | 2992 | 18915 | 17.9s | 0.000 | 0.360 | 0.760 | 0.360 | 0.708 |
| Full-SCC Naive, single attempt | large | 3 | 1 | 1 | 1.000 | 23568 | 3211 | 26779 | 19.1s | 0.000 | 0.000 | 1.000 | 0.000 | 0.807 |
| Full-SCC Naive, single attempt | medium | 11 | 1 | 1 | 1.000 | 24994 | 3684 | 28678 | 20.7s | 0.000 | 0.000 | 0.545 | 0.091 | 0.763 |
| Full-SCC Naive, single attempt | small | 11 | 1 | 1 | 1.000 | 4767 | 2241 | 7008 | 14.9s | 0.000 | 0.818 | 0.909 | 0.727 | 0.626 |
| GraphRAG-style LEA | Overall | 34 | 1 | 1 | 17.941 | 39681 | 25828 | 65509 | 179.6s | 0.000 | 0.735 | 0.941 | 0.441 | 0.517 |
| GraphRAG-style LEA | large | 10 | 1 | 1 | 27.000 | 67101 | 43209 | 110310 | 297.4s | 0.000 | 0.700 | 1.000 | 0.400 | 0.529 |
| GraphRAG-style LEA | medium | 13 | 1 | 1 | 17.154 | 38268 | 26112 | 64380 | 172.4s | 0.000 | 0.692 | 1.000 | 0.308 | 0.512 |
| GraphRAG-style LEA | small | 11 | 1 | 1 | 10.636 | 16424 | 9692 | 26115 | 81.0s | 0.000 | 0.818 | 0.818 | 0.636 | 0.511 |
| SA-MCGS | Overall | 35 | 1 | 1 | 48.971 | 104338 | 67266 | 171603 | 504.6s | 0.000 | 0.857 | 0.914 | 0.743 | 0.518 |
| SA-MCGS | large | 10 | 1 | 1 | 49.300 | 122819 | 78857 | 201676 | 595.3s | 0.000 | 0.600 | 0.700 | 0.400 | 0.529 |
| SA-MCGS | medium | 13 | 1 | 1 | 50.000 | 115088 | 79257 | 194345 | 545.6s | 0.000 | 0.923 | 1.000 | 0.769 | 0.512 |
| SA-MCGS | small | 12 | 1 | 1 | 47.583 | 77291 | 44615 | 121906 | 384.6s | 0.000 | 1.000 | 1.000 | 1.000 | 0.513 |
| naive-single | Overall | 9 | 1 | 1 | None | 43719 | 5332 | 49051 | None | 1.000 | None | None | None | None |
| naive-single | large | 7 | 1 | 1 | None | 46326 | 5386 | 51712 | None | 1.000 | None | None | None | None |
| naive-single | medium | 2 | 1 | 1 | None | 34596 | 5143 | 39738 | None | 1.000 | None | None | None | None |
