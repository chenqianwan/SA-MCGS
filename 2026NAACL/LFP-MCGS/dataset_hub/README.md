# LFP-MCGS Research Hub

This is the compact, local-first research hub for the current Paper 2 position.
The current axis is a topology-controlled SCC intervention protocol inspired by
SA-MCGS:

1. freeze an authority-backed cyclic document graph;
2. minimally place source-grounded `seed / bridge / witness` fragments in
   existing windows without changing its nodes or edges;
3. let the same general LLM acquire local windows under matched test-time
   compute;
4. commit only executed and validated facts/rules;
5. maintain exact incremental LFP closure and feed provenance-aware proof
   obligations back to PUCT.

Controlled intervention establishes mechanism, not natural prevalence. Within
a frozen positive-Horn snapshot, LFP is monotone: it can complete a proof or
derive an explicit signed conflict, but it does not retract an established
closure fact.

## Run locally

Node.js `>=22.13.0` is required.

```bash
npm install
npm run dev
```

Open `http://localhost:3000/`.

Research views:

- `/` — current research conclusion and method loop.
- `/experiment-v3` — current Pure Baseline, real-loop results, and next gates.
- `/review` — nearest prior work and the current dataset shortlist.

Legacy `/experiment-v1`, `/experiment-v2`, and `/wave4` URLs redirect to one of
these current views; the old diagnostic pages are not published.

## Validation

```bash
npm run lint
npx tsc --noEmit
npm test
```

`predev` and `prebuild` run `scripts/sync-dataset-assets.mjs`. It publishes only
six compact Pure Baseline / real-loop summaries and manifests. Raw datasets,
model caches, branch ledgers, and historical experiment artifacts are never
copied into the site bundle.

## Canonical sources

- `../LFP_MCGS_RESEARCH_PLAN_V2.md`
- `../LFP_MCGS_LITERATURE_REVIEW.md`
- `../LFP_MCGS_DATASET_AUDIT.md`
- `app/datasets.ts`
- `app/reviewData.ts`

The primary baselines are ordinary and strong reasoning LLMs under matched
compute. Greedy/Beam/end-only LFP are mechanism controls; TreeMCTS is only the
no-state-sharing ablation.
