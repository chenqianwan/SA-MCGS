# Pre-original LEA runner

`run_pre_lea.py` runs LEA directly on the 18 frozen, unmodified SCCs in
`annotation_prep/candidates/pre_sources_18.json`. It does not invoke defect
injection. The runner verifies both frozen fingerprints and checks that each
reconstructed graph is exactly one Tarjan SCC before any model call.

Validation only (no API calls):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  2026NAACL/SA-MCGS/experiments/lea_update/run_pre_lea.py \
  --output-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_pre_gpt_gemini_20260829_preflight \
  --models gpt-4o gemini-2.5-pro \
  --window-size 4 --case-concurrency 4 --validate-only
```

GPT-4o execution (paid; separate output directory):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  2026NAACL/SA-MCGS/experiments/lea_update/run_pre_lea.py \
  --output-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_pre_gpt18_20260829 \
  --models gpt-4o \
  --window-size 4 --case-concurrency 4
```

The natural-risk diagnostic is frozen as `explicit_pair_v1`: a case asserts a
target conflict only when raw `conflicts` contains two distinct exact SCC IDs
and a nonempty reason. Otherwise it abstains. API, JSON, or schema failure makes
the case invalid, never an abstention. Injected ground-truth, Root, and Risk
metrics are explicitly null in pre-condition results.

The completed GPT-4o run is in `../lea_runs/lea_pre_gpt18_20260829/`: 18/18
cases completed, with 16 valid assertions and two CUAD strict-invalid outputs.
There were no provider/API transport failures. These invalid outputs are kept
as reliability outcomes rather than selectively rerun until successful.

Gemini 2.5 Pro is the second current model. Run it in a separate directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  2026NAACL/SA-MCGS/experiments/lea_update/run_pre_lea.py \
  --output-dir 2026NAACL/SA-MCGS/experiments/lea_runs/lea_pre_gemini18_20260829 \
  --models gemini-2.5-pro \
  --window-size 4 --case-concurrency 2
```

The completed Gemini run is in `../lea_runs/lea_pre_gemini18_20260829/`:
18/18 cases completed, with 17 assertions, one abstention, and zero invalid
outputs. Its call log contains 280 successful API calls and no failed calls or
terminal JSON/schema failures.

The validation preflight reports deterministic window evaluations, not an
exact API-call forecast. Bounded transposition-table reuse is stateful, so the
authoritative call counts are the completed result field `llm_calls` and the
run's `call_logs/llm_calls.jsonl`.
