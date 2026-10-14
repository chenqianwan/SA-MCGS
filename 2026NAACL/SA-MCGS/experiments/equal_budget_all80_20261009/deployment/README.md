# 80-case baseline service allocation

Use the already authorized job 415747 on dgx-061. No new Slurm job is submitted.

Balanced topology: GPU 0/3 Llama, 1/4/6/7 Kimi, 2/5 Qwen. Each server uses one GPU and the exact prior fixed checkpoint, BF16 dtype, context limit, batch limits and generation configuration. Only replica placement changes. Suggested case-arm concurrency: Llama 8, Kimi 12, Qwen 10 per GPU; the scientific worker supervisor owns this setting.

The old supervisor owns all eight children and shuts them all down on any child exit. Therefore the safe transition is a graceful whole-group warm restart. Existing node-local weights and the prior same-model FlashInfer compilation cache are reused. No scientific experiment is run by these scripts. Each replica receives one synthetic maximum-eight-token smoke request; offline token counts must match server usage before endpoints.json is published.

On the login host, run `/usr/bin/python3 -B deployment/start_step_once.py`. It verifies the exact allocation and staged source hashes, records durable intent, and starts a persistent srun step. In that step, `retire_previous.py` checks that all 90 prior finals are terminal and all prior scientific workers exited, verifies supervisor PID 633843 and its command/owner, then sends SIGTERM to exactly Slurm service step 415747.13 (never the parent allocation). No forced kill or job cancellation occurs. The old supervisor cleans up only its own process groups. The new servers start after its exit and port release.

For rollback after stopping new scientific workers, run `/usr/bin/python3 -B deployment/start_step_once.py --rollback`. It gracefully retires this new supervisor and starts the original 3-Llama/3-Kimi/2-Qwen topology. Rollback health receipts and endpoints are isolated under `deployment/rollback_original/`; the scientific runner must explicitly use that endpoints file. This preserves both deployment records. An existing launch receipt prevents duplicate launches; reconcile any failed/ambiguous launch before retrying.

`service_supervisor.py --plan` is offline/read-only. Syntax, both replica maps, and exact per-model command equality against the previous deployment were checked locally. Checkpoint SHA-256 and official metadata are reverified on the node at startup. Runtime versions are pinned to vLLM 0.20.0+cu129, torch 2.11.0+cu128, transformers 5.6.2 and tiktoken 0.12.0.
