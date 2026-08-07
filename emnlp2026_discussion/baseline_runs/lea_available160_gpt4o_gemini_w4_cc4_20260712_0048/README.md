# LEA Available-Model Run

Started: 2026-07-12 01:05 +0800

Scope: 160 cases from `emnlp2026_discussion/case_composition.csv`, covering the currently available models:

- `gpt-4o`: 80 cases
- `gemini-2.5-pro`: 80 cases

Method: GraphRAG-style Local Evidence Aggregation with deterministic local graph windows, window size 4, case concurrency 4.

This run is not a replacement for the intended full-320 table. It is a clean partial run while `deepseek-v3` is blocked by provider quota and `qwen2.5-72b` is unstable/timeout-prone.

Dashboard: `http://127.0.0.1:8765/`

Key outputs while running:

- `status.json`
- `summary_method_cases.csv`
- `summary_lea_full_breakdown.csv` / `summary_lea_full_breakdown.md`
- per-case JSON files under `results/`
