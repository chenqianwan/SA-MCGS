# Initial Discussion Response Matrix

This is a working matrix for planning the author response. It is intentionally conservative: claims and new experiment numbers should be filled only after checking the paper, logs, and available time budget.

| Concern cluster | Reviewers | What they asked | Possible response direction | Evidence/action needed |
|---|---|---|---|---|
| Component-level ablations | iMEC, rxvy | Isolate SA-MCGS modules beyond the TreeMCTS failure diagnosis | Report or commit to additional ablations: relation memory, OC signal, critical-pair ledger, replacement vs monotone core, random local-window selection | Check existing supplement logs; run feasible ablation subset if missing |
| Inference cost | iMEC, wWUk, rxvy | Report input/output tokens, calls, runtime, latency/cost tradeoff | Add a compact cost table and explain budget comparability | Extract token/call/runtime logs or rerun accounting scripts |
| Baseline fairness | iMEC, rxvy, wWUk | Add graph-aware/local-window baselines; address prompt decomposition and schema difficulty | Clarify oracle-risk Naive as a ground-truth-selected boosted full-SCC baseline; add GraphRAG-style Local Evidence Aggregation (LEA): deterministic graph windows + same local schema + transparent aggregation, without SA-MCGS memory/search/core modules | Use existing E0/E1/E5 for fairness checks; implement LEA on stratified cases and report with costs |
| Injected vs natural risks | rxvy, wWUk | Weaken real high-stakes claims or add naturally occurring cases | Reframe benchmark as controlled structural-risk evaluation; cite expert audit carefully; add negative/natural examples if available | Check human annotation pack and any naturally occurring risk cases |
| Negative cases / over-reporting | rxvy | Add clean or non-risk SCCs; show false positive behavior | Report a small clean-SCC evaluation or add limitation if not feasible | Search datasets for clean SCCs; compute over-report/irrelevant-node rates |
| Model-specific non-uniformity | iMEC, rxvy | Discuss Gemini 2.5 Pro and DeepSeek-V3 cases where Naive is strong | State that gains are largest under long/noisy SCCs and reliability-stressed settings; avoid uniform-superiority framing | Pull model breakdown table and exact deltas |
| Subgraph precision / irrelevant nodes | rxvy | Compression is not enough; measure cleanliness | Report irrelevant-node rate or precision-like endpoint/non-endpoint measure | Derive from retained subgraph annotations if available |
| Prior coefficient sensitivity | rxvy | Show stability under perturbations | Add sensitivity note/table for fixed priors | Check coefficient scripts; run small perturbation grid if feasible |
| Technical contribution significance | iMEC | Concern that contribution is task-specific integration | Emphasize cyclic-SCC failure formulation, relation-indexed memory, SCC-aware rollout/control, dynamic core as unified method | Anchor response in paper equations/algorithm and empirical failure mode |
| Societal impact | rxvy | Clarify decision-support use and overtrust risk | Add sentence to limitations/discussion: decision support, not automated adjudication | Draft concise limitation language |
| Writing / typo | iMEC, rxvy | Fix "Appendix 9" typo; define "oracle-risk Naive" clearly | Acknowledge and promise correction | Locate exact typo and definition site |
