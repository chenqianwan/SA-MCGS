# GPT-4o slot04 Full-SCC: selector-only recovery

This directory preserves the original failed result. It does not rerun SA, regenerate candidates, retry an unknown request, or revise the original experiment files.

The original arm completed 11 valid candidates before an `APIConnectionError` interrupted candidate 12. Its ledger has 11 successful requests and two unknown outcomes (one returned HTTP 503 and one connection error). The protocol keeps all 30,934 reserved tokens for these unknown outcomes. Known usage is 49,275 tokens; accounted usage is 80,209 against the unchanged 99,876-token ceiling.

Recovery ends candidate sampling and runs the original anonymous, label-blind selector once on all 11 complete candidates. It preserves the original seed 42, candidate projections, prompt, temperature 0 and 256-token output allowance. The estimated selector reservation is 3,481 tokens, below the remaining 19,667. Estimates are not provider-enforced bounds; actual provider usage settles the ledger and any overrun remains visible.

`source_snapshot/` retains the complete original cell files, including the ledger, raw request/response logs, candidates and original failed final. `protocol.json` freezes their hashes, code dependencies, candidate order, prompt and exact selector request hash. `result/` is a separate continuation ledger and final. Old and new ledgers overlap intentionally: add only `new_selector_usage` when reporting incremental cost; do not double-count the copied historical prefix.

The only relaxed guard permits the one frozen selector request to follow the two explicitly identified, fully reserved old unknown outcomes. No SDK retry, JSON retry, transport retry or fallback selection is allowed. A durable launch intent prevents automatic reissue after an interrupted selector. Existing finals are never selected based on score or overwritten.

Offline preparation (default; no credentials or network):

```sh
/Users/chenlong/.pyenv/versions/3.11.0/bin/python3 -B run_selector.py --prepare
```

Explicit execution, only when authorized:

```sh
/Users/chenlong/.pyenv/versions/3.11.0/bin/python3 -B run_selector.py --run
```

The final contains the selected original candidate, unchanged science metrics, full cumulative accounting, incremental selector usage, source hashes and recovery provenance. A failed selector remains failed with no fallback. This is a documented continuation after an infrastructure failure, not a new independent Full-SCC sample.
