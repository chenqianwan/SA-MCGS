# LEA coverage before completion

Frozen scope: the same 80 stable cases on all four original models (320 cells).
Only the four audited legacy/repair batches are eligible for reuse. No cost-audit or exploratory runs are imported.

| Model | Exact reuse | Missing | Identity repairs | Total to run |
|---|---:|---:|---:|---:|
| gpt-4o | 74 | 0 | 6 | 6 |
| gemini-2.5-pro | 73 | 0 | 7 | 7 |
| qwen2.5-72b | 0 | 80 | 0 | 80 |
| deepseek-v3 | 0 | 80 | 0 | 80 |
| Total | 147 | 160 | 13 | 173 |

The input CSVs use each model's original SA result and resolve every source path to this checkout. Stable physical SCC IDs, ordered clause IDs, injection identities, graph fingerprints, source hashes, and original case orders are frozen in `frozen_manifest.json`.

Preflight rebuilds the runner plan from the CSV, validates every source and graph identity, and replays each injection without calling any API.
Preflight status: passed for 173 cases; API calls = 0.

Rebuild: `python3 2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/build_manifest.py`

The paid experiment must use the separate budget-controlled runner. The user authorized a total ceiling of USD 50 for this completion batch.
