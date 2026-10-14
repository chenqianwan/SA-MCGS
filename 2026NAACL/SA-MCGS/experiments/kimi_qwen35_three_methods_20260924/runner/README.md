# Portable two-model experiment runner

The required deployment files are `generic_launcher.py`, the unchanged
`base_launcher.py`, and the complete `repo/` directory. Each model uses its own
configuration and output directory. The supervisor owns model deployment and
worker scheduling; all generation routes are restricted to localhost.

Example from the experiment root, using the deployment Python environment:

```sh
PYTHONHASHSEED=42 python -B runner/generic_launcher.py --model-config configs/kimi.json --output-dir results/kimi --mode tokenize --tokenizer-path models/kimi
PYTHONHASHSEED=42 python -B runner/generic_launcher.py --model-config configs/kimi.json --output-dir results/kimi --mode smoke --tokenizer-path models/kimi
PYTHONHASHSEED=42 python -B runner/generic_launcher.py --model-config configs/kimi.json --output-dir results/kimi --mode run --tokenizer-path models/kimi --case-concurrency 8 --shard-count 8 --shard-index 0
PYTHONHASHSEED=42 python -B runner/generic_launcher.py --model-config configs/kimi.json --output-dir results/kimi --mode summarize
```

Launch one worker for each shard index 0 through 7. For Qwen, use
`configs/qwen35.json`, `results/qwen35`, and `models/qwen35`. Fixed smoke case 20
counts toward the planned experiment and is skipped when workers encounter it.
`preflight` validates identities and captures prompts without loading a tokenizer
or making any API requests. `tokenize` additionally validates the local tokenizer
and available context. Runtime checks cover dynamic SA prompts without truncation.

Scientific code files are verified against their original hashes. One-shot uses
the original strict direct-subgraph implementation with 12,000 output tokens.
The adapter disables the historical hosted-Qwen name-based 8,192-token cap only
for this new local Qwen model. Qwen thinking is disabled in both tokenizer and
generation requests. LEA and SA retain window 4, temperature 0.4, and 2,048 output
tokens. SA uses B60 and internal concurrency 8. Python RNG and hash seeds are 42,
as specified for these new local experiments.

Scientific results remain in `results/`, with terminal status `complete` or
`strict_experiment_failure`. Infrastructure failures reside exclusively in
`infrastructure_failures/` and receive no scientific prediction. Valid completed
results are immutable and are reused. Exact request caches and completion ordering
support resumption; an inconsistent checkpoint is preserved and recorded as an
infrastructure failure, never silently discarded.

A healthy `/models` endpoint means a failed generation request skips only its cell.
Transport/timeout/408/429/5xx failures trigger exit 75 only if the authenticated
three-second health probe also fails to find the configured model alias. The
supervisor may then perform its bounded endpoint recovery. Persistent per-cell
attempt counters default to 4 and never reset on worker restarts. Global frozen
configuration errors exit 78. After recovery is exhausted, the supervisor may
invoke `--mode finalize-infrastructure --infrastructure-reason TEXT` to settle only
unresolved cells. The final summary distinguishes scientific results from these
operational skips.

Run the network-free regression checks from this directory:

```sh
PYTHONHASHSEED=42 python -B -m unittest -v test_generic_launcher.py
```
