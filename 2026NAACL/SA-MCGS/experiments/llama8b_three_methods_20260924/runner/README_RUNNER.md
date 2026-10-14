# Llama 3.1 8B: three-method portable runner

`llama_launcher.py` is an infrastructure adapter around unchanged scientific code in `repo/`. It calls the existing `run_cost_audit_clean.run_method` for One-shot (`naive-single`, strict `direct_subgraph`), LEA, and SA-MCGS. The copied four-domain graphs and 80 ordered-clause/injection identities are verified against their original content hashes before any model call. Changing model/case labels does not change the stable case UID.

Scientific settings: SA B60, window4, temperature0.4, output2048, internal concurrency8; LEA window4, temperature0.4, output2048, sequential; One-shot temperature0, output12000, sequential. JSON parsing allows three calls, followed by the original `{}` fallback. SA concurrency8 matches the historical GPT/DeepSeek experiment; old Qwen used12, old Gemini used10 in76 cases and12 in4. Python RNG seed42 and `PYTHONHASHSEED=42` are explicit new reproducibility settings, not claims about historical runs.

Deploy only `llama_launcher.py` and the complete `repo/` directory at the same relative positions. The tests/README may be included; local offline validation folders are not deployment inputs. All workers and the model server must run inside the SAME Slurm node. The only allowed route is `http://127.0.0.1:18081/v1`, alias `llama-3.1-8b-instruct`; no external paid API is used. Hardware/node/time allocation belongs to the parent coordinator.

Every invocation requires `PYTHONHASHSEED=42`, `--output-dir`, and `--checkpoint-revision`. Modes `preflight`, `tokenize`, `smoke`, `run`, and `summarize` share the same frozen protocol. `--tokenizer-path` is required for tokenize/smoke/run; `--max-model-len` defaults131072; `--case-concurrency2` records scheduling, while `--shard-count2 --shard-index0/1` select independent sequential case shards. Preflight and tokenize make zero API calls. Smoke uses fixed case20 for all three methods and those observations count toward the final240; strict scientific failures remain terminal and do not gate other cases.

Example (paths supplied by the coordinator):

```sh
PYTHONHASHSEED=42 "$PYTHON" llama_launcher.py --mode tokenize --output-dir "$OUTPUT" --tokenizer-path "$MODEL_PATH" --checkpoint-revision 0e9e39f249a16976918f6564b8830bc894c89659 --max-model-len 131072 --case-concurrency 2
PYTHONHASHSEED=42 "$PYTHON" llama_launcher.py --mode run --output-dir "$OUTPUT" --tokenizer-path "$MODEL_PATH" --checkpoint-revision 0e9e39f249a16976918f6564b8830bc894c89659 --max-model-len 131072 --case-concurrency 2 --shard-count 2 --shard-index 0
```

Tokenization checks all80 full-SCC One-shot prompts and1344 deterministic LEA windows, plus one empty-JSON SA trajectory. Because SA prompts depend on live search state, the latter does not exhaust possible SA requests: every actual request is tokenized again and blocked on overflow, never truncated. Tokenizer file hashes are pinned. Before tokenization succeeds the model is never called.

Response caches are isolated per case/method. `requests.jsonl` includes exact messages and generation parameters; `responses.jsonl` includes raw text, usage, returned model, finish reason, and durable completion order. Resume verifies every old invocation's request hash, then releases old replies in recorded completion order. New replies wait until the old completion prefix has replayed. Any old-prefix mismatch stops; no silent alternate sampling. The order and contents of genuinely unreturned new replies may change, as in any concurrent sampling continuation.

A transport/identity/config failure propagates outside the original scientific exception handler and leaves a resumable case status. An actual output-format/schema failure is retained as `strict_experiment_failure`. Summary verifies each saved identity/config and scores strict failures as zero detection, with compression undefined. Completion means80×3 terminal results, not240 valid predictions. It exports `summary.json` with `verification_passed`, `expected_results=240`, `terminal_results`, and per-method metrics, plus `case_metrics.csv`.

Offline tests exercise actual unchanged SA with8 concurrent tasks, deliberately reordered replies, nonuniform risk scores/critical-pair memory, a JSON retry, full checkpoint replay, and partial-batch interruption/resume. A deterministic local fake server controls the remaining reply order when comparing the complete counterfactual trajectory. Separate tests verify transport errors bypass scientific fallback and One-shot malformed output remains a scientific error. No tests call a real model.
