| Model | Method | Planned | Attempted | Valid | Invalid | Missing | Invalid rate / planned | Logical calls / planned | Recorded calls / planned | Input tok. / planned | Output tok. / planned | Total tok. / planned | Total tok. median attempted | Runtime / planned | Runtime median attempted | Root@3 strict | Risk-any strict | Risk-all strict | Compression mean valid-only | Compression n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o | One-shot (full-SCC, single attempt) | 12 | 12 | 9 | 3 | 0 | 0.250 | 0.8 | 1.0 | 16978.4 | 2941.3 | 19919.8 | 8022.0 | 20.967 | 22.141 | 0.333 | 0.583 | 0.250 | 0.672 | 9 |
| gpt-4o | GraphRAG-style LEA | 12 | 12 | 12 | 0 | 0 | 0.000 | 16.9 | 17.8 | 36304.1 | 22776.8 | 59080.8 | 32093.5 | 189.163 | 137.959 | 0.833 | 0.917 | 0.417 | 0.510 | 12 |
| gpt-4o | SA-MCGS | 12 | 12 | 12 | 0 | 0 | 0.000 | 57.2 | 59.6 | 112251.6 | 68418.4 | 180670.0 | 176320.0 | 570.897 | 574.744 | 0.917 | 1.000 | 0.833 | 0.510 | 12 |
| gemini-2.5-pro | One-shot (full-SCC, single attempt) | 12 | 12 | 12 | 0 | 0 | 0.000 | 1.0 | 1.0 | 19553.7 | 7502.3 | 27056.0 | 13848.5 | 85.885 | 66.774 | 1.000 | 1.000 | 1.000 | 0.693 | 12 |
| gemini-2.5-pro | GraphRAG-style LEA | 12 | 12 | 12 | 0 | 0 | 0.000 | 15.8 | 15.9 | 36594.3 | 31728.2 | 68322.5 | 53169.5 | 868.234 | 443.933 | 0.750 | 1.000 | 0.833 | 0.510 | 12 |
| gemini-2.5-pro | SA-MCGS | 12 | 12 | 12 | 0 | 0 | 0.000 | 51.4 | 53.5 | 115897.2 | 110161.4 | 226058.7 | 221469.5 | 1650.232 | 1413.088 | 0.917 | 1.000 | 0.917 | 0.574 | 12 |
| Both models | One-shot (full-SCC, single attempt) | 24 | 24 | 21 | 3 | 0 | 0.125 | 0.9 | 1.0 | 18266.0 | 5221.8 | 23487.9 | 12096.5 | 53.426 | 31.045 | 0.667 | 0.792 | 0.625 | 0.684 | 21 |
| Both models | GraphRAG-style LEA | 24 | 24 | 24 | 0 | 0 | 0.000 | 16.3 | 16.9 | 36449.2 | 27252.5 | 63701.7 | 45978.5 | 528.698 | 315.756 | 0.792 | 0.958 | 0.625 | 0.510 | 24 |
| Both models | SA-MCGS | 24 | 24 | 24 | 0 | 0 | 0.000 | 54.3 | 56.5 | 114074.4 | 89289.9 | 203364.3 | 205857.5 | 1110.565 | 908.860 | 0.917 | 1.000 | 0.875 | 0.542 | 24 |
