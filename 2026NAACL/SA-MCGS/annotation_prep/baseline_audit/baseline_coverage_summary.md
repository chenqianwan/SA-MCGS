# Baseline coverage audit

- Candidate manifest: `2026NAACL/SA-MCGS/annotation_prep/candidates/selected_post_36.json`
- Post variants: **36**
- Models: `gpt-4o, gemini-2.5-pro`
- Coverage cells: **216**
- Cells requiring rerun: **0**

| model | method | available exact | strict invalid (kept) | identity mismatch | missing | rerun |
|---|---|---:|---:|---:|---:|---:|
| gpt-4o | one-shot | 29 | 7 | 0 | 0 | 0 |
| gpt-4o | sa-mcgs | 36 | 0 | 0 | 0 | 0 |
| gpt-4o | lea | 36 | 0 | 0 | 0 | 0 |
| gemini-2.5-pro | one-shot | 36 | 0 | 0 | 0 | 0 |
| gemini-2.5-pro | sa-mcgs | 36 | 0 | 0 | 0 | 0 |
| gemini-2.5-pro | lea | 36 | 0 | 0 | 0 | 0 |

Interpretation: a locked one-shot invalid output remains a valid strict outcome and is not rerun. Only missing or identity-mismatched cells enter `rerun_scope.csv`. Numeric Tarjan `scc_id` is diagnostic only.
