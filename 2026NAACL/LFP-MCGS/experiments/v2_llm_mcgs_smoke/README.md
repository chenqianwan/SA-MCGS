# Experiment V2 · local-LLM LFP-MCGS integration smoke

## Verdict

**PASS as an integration smoke; not a method result.**

The complete online path now executes:

```text
public query + raw sources
  → symbol-free MCGS sketch planning
  → execute one root source action
  → local Qwen parse + fail-closed validation
  → query-local Horn KB
  → exact least-fixed-point closure
  → source-set proof check or replan
```

No policy or rollout receives the answer, gold MAC/proof, a source's formal
representation, or an unexecuted LLM parse. The fixed online budget is 10 real
source actions per case.

## Frozen smoke

- Data: four productive ProofWriter D5 dev cases + two Unknown cycle controls.
- Parser: local `qwen2.5:14b`, temperature 0, one source per call.
- Search: Random, surface-obligation Greedy, sketch Greedy, TreeMCTS, and
  state-sharing MCGS; three seeds each.
- TreeMCTS and MCGS share the same public-text sketch, horizon, simulations,
  reward, root budget, and deterministic tie stream. Only abstract state sharing
  differs.

## R2 result

| Check | Result |
|---|---:|
| Query parse exact | 6 / 6 |
| Source parse semantic exact | 100 / 100 |
| Extract-All productive recovery | 4 / 4 cases |
| Extract-All Unknown sanity | 2 / 2 PR-Unknown |
| LFP-MCGS proof recovery | 11 / 12 productive trials; 4 / 4 cases |
| TreeMCTS proof recovery | 11 / 12 productive trials; 4 / 4 cases |
| Unknown false entailment | 0 / 30 trials across all policies |
| Abstract MCGS transposition hits | 1,984 |
| Search nodes | MCGS 6,933 vs TreeMCTS 8,974 (22.7% fewer) |

All returned endpoints pass an independent **source-set sufficiency** check:
re-running exact LFP on only the cited source set still derives the endpoint.
This is not yet a stepwise proof-DAG certificate.

## What changed after R1 failed

R1 used an undirected bag-of-words sketch. It repeatedly selected a rule with
the right vocabulary but left one bridge source unread; MCGS recovered 0/12
productive trials. R2 uses a cheap, public-text-only head/body direction sketch
conditioned on the current real LFP frontier. It still emits no Atom, Rule, or
hypothetical proof and cannot inspect the hidden local parse.

This is nevertheless a **strong, uncharged shortcut** on the frozen slice: an
independent audit found that the hand-written sketch recovered the source
fact/rule kind and the head/body predicate sets for all 100 source instances.
It is not a direct gold or hidden-outcome leak, but it is close to a free
predicate-level parser. Therefore R2 validates integration only. A confirmatory
run must replace it with a frozen, charged outcome model and compare against
one-step and beam policies with exactly the same access.

The R1 result is preserved under `results/attempt1_failed/`.

## Claim boundary

R2 establishes that local semantic parsing, root-only acquisition, branch-local
knowledge, exact closure, multi-step search/backpropagation, abstract
transpositions, and source-set proof checking can run together without the
known gold/hidden-outcome leaks.

It does **not** establish:

- accuracy superiority over TreeMCTS (both are 11/12);
- a learned or model-general outcome simulator;
- real committed-program state merging, subtree reuse, or token savings;
- closure-delta reward backpropagation inside hypothetical rollouts;
- a stepwise proof DAG or end-to-end natural-language soundness;
- productive-SCC causality versus a matched DAG;
- revision, legal-domain transfer, statistical significance, or generalization.
- the current Paper 2 architecture: persistent committed KB across executed local
  windows, online incremental-LFP feedback inside SA-MCGS/PUCT, or a matched-compute
  advantage over general-purpose LLM baselines.

## Reproduce

```bash
python3 2026NAACL/LFP-MCGS/experiments/v2_llm_mcgs_smoke/run_v2_smoke.py
```

The run requires local Ollama with the frozen model digest in `config.json`.
The manifest hashes the config, runner, reference LFP engine, dataset snapshot,
parser cache, parser audit, trials, and result summary.
