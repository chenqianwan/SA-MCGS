# Cost / reliability and relation-prior sensitivity

This directory is a frozen, identity-safe supplement for the SA-MCGS paper.
It intentionally does not edit the shared revision plan or any earlier result
directory.

Main cost table:

- 12 frozen physical SCCs, selected without looking at new outcomes;
- GPT-4o and Gemini 2.5 Pro;
- one-shot full-SCC prompting, GraphRAG-style LEA, and SA-MCGS;
- locked main-paper settings: `memory_stress`, `structural_simple_v2`, critical,
  current/default compression, SA budget 60;
- case and internal LLM concurrency both fixed to one;
- all binary metrics use the full frozen denominator.

Prior sensitivity:

- the same 12 cases and two models;
- only `alphago_mcgs.evidence.relation_prior_weight` changes;
- nominal 0.85, minus 20% (0.68), and plus 20% (1.02);
- nominal results are strictly reused from the cost run and are never rerun.

The API key is read from the repository's ignored `.env` file by the existing
runner. The key and the unfiltered XHub usage response are never written here.

Typical commands (from the repository root, using the environment that has the
project dependencies):

```bash
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/run_cost_prior.py preflight
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/run_cost_prior.py cost-smoke
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/run_cost_prior.py cost
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/run_cost_prior.py prior
/opt/homebrew/anaconda3/bin/python 2026NAACL/SA-MCGS/experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1/run_cost_prior.py report
```

All commands resume safely from completed result JSON files. Failed cells are
retained. Retrying a failed cell requires the explicit `--retry-errors` flag;
the original result is first copied to an immutable attempt-history path.
