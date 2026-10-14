# GPT-4o + Gemini 2.5 Pro LEA update

This directory freezes the identity-safe LEA repair for the 36 post variants. Case selection is structural and does not read model outcomes.

## Current scope

- GPT-4o: 12 SEC identity repairs, completed on 2026-08-29.
- Gemini 2.5 Pro: 11 SEC identity repairs completed on 2026-08-29; `post_006` already had an exact legacy result and was not rerun.
- Current frozen repair scope: 23 model-case jobs.

Rebuild the scope:

```bash
python3 2026NAACL/SA-MCGS/experiments/lea_update/build_post_scope.py
```

This produces `post_lea_gpt_gemini_scope.json`, `post_lea_gpt12_cases.csv`, `post_lea_gemini11_cases.csv`, and non-overlapping Gemini smoke/remaining CSVs.

Gemini execution:

```bash
python3 emnlp2026_discussion/run_lea_full_baseline.py \
  --case-csv 2026NAACL/SA-MCGS/experiments/lea_update/post_lea_gemini_smoke_1_case.csv \
  --output-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_smoke_20260829 \
  --models gemini-2.5-pro --window-size 4 --case-concurrency 1

python3 emnlp2026_discussion/run_lea_full_baseline.py \
  --case-csv 2026NAACL/SA-MCGS/experiments/lea_update/post_lea_gemini_remaining10_cases.csv \
  --output-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_remaining10_20260829 \
  --models gemini-2.5-pro --window-size 4 --case-concurrency 2
```

Final coverage audit must merge the legacy GPT/Gemini LEA directory, the new GPT-12 directory, and both new Gemini directories.

The merged audit now has 36/36 exact LEA results for each model and zero
remaining rerun cells. On this frozen 36-case subset, GPT-4o obtains Root@3
75.0%, Risk-any 94.4%, and Risk-all 27.8%; Gemini obtains Root@3 88.9%,
Risk-any 100%, and Risk-all 83.3%. These are subset diagnostics, not a
replacement for the rebuttal matched-160 results.

## Historical Qwen attempt

The earlier Qwen-target scope CSVs, `post_lea_scope.json`, Qwen preflight, and failed provider smoke are retained unchanged as audit history. They are superseded and are not part of the current paper model pair. Candidate/internal manifests may also contain Qwen legacy provenance; those fields must not be rewritten.

The pre-original runner and frozen abstention rule are documented in `PRE_LEA_RUNNER.md`.
