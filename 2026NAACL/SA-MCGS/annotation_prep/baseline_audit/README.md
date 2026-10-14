# Baseline coverage audit

This directory audits stored baselines for the frozen 36 post-injection cases. It never calls a model API.

The current comparison pair is **GPT-4o + Gemini 2.5 Pro**. The 36 structural variants are model-independent.

Run the final audit by merging legacy and identity-repair LEA directories:

```bash
python3 2026NAACL/SA-MCGS/annotation_prep/baseline_audit/audit_baseline_coverage.py \
  --manifest 2026NAACL/SA-MCGS/annotation_prep/candidates/selected_post_36.json \
  --models gpt-4o,gemini-2.5-pro \
  --lea-dir emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048/results \
  --lea-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gpt12_20260829/results \
  --lea-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_smoke_20260829/results \
  --lea-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_post_gemini_remaining10_20260829/results
```

When multiple directories contain the same model-case, the audit prefers an exact-identity artifact over an identity-mismatched artifact and fails on ambiguous duplicate exact artifacts.

Outputs:

- `baseline_coverage.csv`: one row per candidate × model × method.
- `rerun_scope.csv`: only missing or identity-mismatched cells.
- `baseline_coverage_summary.{json,md}`: compact totals.

Identity rules:

- Source clustering uses an injection-text-independent source physical fingerprint/UID.
- A post variant is matched by stable variant identity; `domain + size + template` is allowed only when unique in the locked catalog and is recorded as a fallback.
- The injection-sensitive planned SCC fingerprint is not used as a source-cluster identifier.
- Tarjan `scc_id` is diagnostic only.
- A locked one-shot invalid output is a strict experimental outcome, not a missing baseline, and is not rerun.

Current audit history:

- Locked one-shot and SA-MCGS cover all 36 cases for both GPT-4o and Gemini 2.5 Pro. GPT-4o has seven locked one-shot invalid outputs; Gemini has none.
- Before repair, GPT LEA had 24 exact + 12 identity mismatches; Gemini LEA had 25 exact + 11 identity mismatches.
- GPT's 12 repairs and Gemini's 11 repairs completed on 2026-08-29; the current post audit has zero rerun cells.
- The earlier GPT/Qwen scope and provider failure are retained as superseded audit history; Qwen is not in the current model pair.
