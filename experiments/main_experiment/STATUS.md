# Main Experiment Status

## Locked

- Main experiment data: done.
- Dashboard aggregation: done.
- Main result scope: locked.

## Supplement Experiments

- E0 matched / valid-only / matched-no-error: done.
- E1 Naive output-burden control on CUAD long SCCs: done.
- E2 budget-prefix convergence from SA-MCGS traces: done.
- E3 compression profile ablation: done.
- E4 human audit for BGB/CUAD cases: owned by user.
- E5 prompt / rubric parity: done.
- Paper-facing figures and tables under `supplements/`: done.

## Still Needed For Paper

1. Use `current/default + critical + 80 cases x 4 models` as the only main-table scope.
2. Write baseline fairness and error-handling paragraph using E0/E1/E5.
3. Replace cumulative Effective OC wording with discovery/retention/persistence wording using E2.
4. Write compression trade-off paragraph using E3.
5. Add E4 human audit once available.
6. Write two case studies.
7. Rewrite LaTeX after the supplement evidence above is frozen.

## Do Not Change

- Do not rerun the main experiment unless a reproducibility bug is found.
- Do not add more models to the main table.
- Do not swap `current/default` for `balanced` in the main table.
- Do not include Gemini 2.5 Flash in the main result.
