# Qwen2.5-72B: 80-case equal-budget experiment

This run executes LEA and Full-SCC on the same frozen 80 cases used by the other equal-budget experiments. The 80 historical SA-MCGS results are reused unchanged. The authorized scope is one wave: 160 new baseline results and 240 comparison rows. No SA inference is scheduled.

## Budget

Historical Qwen2.5 SA files record algorithm-level LLM calls but no token usage. For each exact case, the frozen baseline cap is:

`ceil(historical SA algorithm calls × historical Qwen2.5 LEA total tokens / historical Qwen2.5 LEA algorithm calls)`

The LEA token numerator includes all actual API attempts, including JSON retries. Each baseline receives its own independent copy of the case cap. The 80 caps sum to 21,845,284 tokens per baseline (43,690,568 across both baselines); individual caps range from 86,029 to 573,855. Actual baseline generation, retry and selector usage is recorded against the cap. Unknown usage stops the affected worker with its reservation preserved.

`historical_sa_raw_reference.json` retains missing historical usage as null. `historical_sa_reference.json` provides the runner's derived cap and its `calibrated` provenance. The estimate is never reported as measured SA token usage. The model's display name remains Qwen2.5-72B. Source results, logs, hashes and the reproducible calculation are preserved under `sources/`, `budget_sources.json` and `prepare_budget.py`.

## Scientific configuration

The case plan, injected case identities, baseline implementation and token accounting implementation match `equal_budget_all80_20261009`. `methods_full.py` and `budget_client.py` are byte-identical to that comparator. Candidate generation and anonymous same-model selection follow the existing method. Seed 42, candidate temperature 0.4, selector temperature 0, LEA window 4/output 2048, Full-SCC output 12000, selector output 256, JSON attempts 3, selector attempts 1 and SDK retries 0 are retained. The hosted Qwen-specific 8192 output clamp is explicitly bypassed for this local run to retain the comparators' 12000 Full-SCC allowance.

All 80 cases are retained in strict success denominators. Invalid outputs score zero; compression is averaged over valid outputs, matching the GPU comparator. Ground truth is used only for identity verification and offline metrics.

## Cluster execution

Existing allocation 415747 on dgx-061 is reused. The checkpoint is `Qwen/Qwen2.5-72B-Instruct-AWQ` at revision `698703eae6604af048a3d2f509995dc302088217`, matching the earlier local Qwen deployment. Restored weights are independently verified against the pinned official metadata.

The longest frozen Full-SCC prompt has 67,179 input tokens and requires 79,179 tokens including its output allowance. Four tensor-parallel-2 replicas use the eight H800 GPUs, FP16, a 131072 context, and the official YaRN factor 4 configuration supplied at service launch. Original checkpoint files remain unchanged. Initial execution concurrency is four independent arm workers per replica (16 workers total). The service and worker launchers use durable receipts and do not launch duplicates on repeated invocation.

`deployment/context_preflight.py` tokenizes all case prompts without model calls. `runner.py --prepare` checks the science bundle, case identities, frozen scope and budgets without model calls. Services publish endpoints only after their health and synthetic token-count checks pass. `start_workers_once.py` starts the verified baseline queue. `report_results.py` generates comparison summaries from completed arms and the frozen SA reference. Completion requires all 160 new arms; deployment readiness alone is not experiment completion.

`deployment/start_pipeline_once.py` dispatches the persistent controller in the existing allocation. It waits for verified model restoration, rechecks completion and idleness of the old experiment services, retires their exact supervisor, starts the new services, then starts the baseline workers. It remains alive while the nested Slurm steps run. It records each phase in `deployment/pipeline_status.json` and stops this run's services after the experiment ends. It never retries a failed scientific arm automatically.

The deployed runtime preflight is recorded in `preflight/cluster_validation.json`: the portable tests, frozen budget calculation, 80-case scope, effective YaRN parameters and full prompt contexts passed before service launch. The initial old-service check is in `preflight/previous_service_idle_check.json`; that check sent no signal.
