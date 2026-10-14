# Eight local model replicas

This deployment uses existing Slurm allocation **415747**, node **dgx-061**.
It starts no new allocation and never cancels the parent allocation.
All three checkpoints reuse the previous successful BF16, single-H800 setup:
131072 context, TP=1, eager execution, disabled async scheduling, memory fraction
0.85, chunked prefill, batch token cap 8192. Qwen keeps thinking disabled.
No model is quantized or changed. Runtime versions and complete checkpoint hashes
are checked before launch; source/config/tokenizer hashes are recorded separately.

The previous personal model directories retained their configuration files but
their weight shards had been removed. `restore_models.py` copies available pinned
bytes and downloads missing bytes without credentials; every file must match the
previously frozen official revision/hash. A brief shared-filesystem restore hit
the account quota despite filesystem-wide free space. Only this experiment's new
model files were moved to `/tmp/chenlong_mcgs_415747/models` on dgx-061, with a
persistent migration receipt. All further model downloads use that private node
directory (1.78 TB free at preflight). Complete model hashes are checked before
serving. The node cache is temporary; results, provenance, and logs remain under
the persistent experiment root. Earlier failed/retired steps and receipts are
preserved under `history/`. No old experiment data or shared weights were changed.

| GPU ordinal | Model | Replica | Port |
|---|---|---|---|
| 0 | Llama 3.1 8B Instruct | llama-0 | 19081 |
| 1 | Kimi VL A3B Instruct | kimi-0 | 19082 |
| 2 | Qwen3.5 9B | qwen35-0 | 19083 |
| 3 | Llama 3.1 8B Instruct | llama-1 | 19084 |
| 4 | Kimi VL A3B Instruct | kimi-1 | 19085 |
| 5 | Qwen3.5 9B | qwen35-1 | 19086 |
| 6 | Llama 3.1 8B Instruct | llama-2 | 19087 |
| 7 | Kimi VL A3B Instruct | kimi-2 | 19088 |

The ordinal is mapped through Slurm's CUDA_VISIBLE_DEVICES. Services bind only to
127.0.0.1 and experiment workers must run on the same node. The first three
services must pass health and one eight-token synthetic smoke request each before
the remaining five start. Smoke request/response usage is stored separately and
does not enter scientific results. No real case is sent by deployment code.

`start_step_once.py` checks the allocation and staged hashes, records a persistent
launch intent, and starts a detached `srun --overlap --exact` step with 80 CPUs and
8 GPUs. A preexisting receipt prevents duplicate launch, including after ambiguous
SSH disconnects. Inspect `step_launch_receipt.json`, `step.log`, and
`service_state.json` before considering recovery; do not delete a receipt to retry.

`service_supervisor.py` owns only its eight child process groups. It keeps caches
under the new experiment root and uses private short /tmp paths for vLLM sockets.
Shared environments/checkpoints are read-only and downloads are disabled.
It publishes `../endpoints.json` only after all eight health checks and synthetic
smokes pass. Check `service_state.json.status == "ready"` before starting workers.
After startup, three consecutive failed endpoint health checks or a server exit
stop this supervisor's services and preserve logs. There is no automatic restart
or automatic replay of experiment requests.

Root-owned experiment workers use deterministic case-ordinal modulo replica-count
partitioning. All three methods for a case stay on its assigned replica. This
deployment does not alter case seeds, algorithm parameters, retry policies, or
scientific token budgets. The user subsequently limited the first experiment to
10 cases x 3 models x 3 methods (90 results); only the root-owned worker enforces
that scope. Deployment itself sends no real case.
