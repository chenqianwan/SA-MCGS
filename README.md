# SA-MCGS: Structure-Aware Monte Carlo Graph Search for Legal Risk Evaluation

## Paper-Stage Status

The project is now in **ARR/EMNLP paper-writing mode**. The main experiment is locked at the file level:

- Main experiment entry: [`experiments/main_experiment/`](experiments/main_experiment/)
- Paper supplement entry: [`experiments/main_experiment/supplements/`](experiments/main_experiment/supplements/)
- Main scope: `current/default + critical + 80 cases x 4 models`
- Models: `gpt-4o`, `deepseek-v3`, `qwen2.5-72b`, `gemini-2.5-pro`
- Domains: Debian, SEC EX-21, BGB, CUAD
- Methods: Naive direct-subgraph vs SA-MCGS
- SA-MCGS budget: 60 rollouts

Use [`experiments/main_experiment/MANIFEST.json`](experiments/main_experiment/MANIFEST.json) as the canonical source list for paper tables, figures, and case studies. Results outside this scope are appendix, ablation, diagnostic, or exploratory only.
The required supplement experiments E0/E1/E2/E3/E5 are generated under `experiments/main_experiment/supplements/`; E4 is the remaining human audit.

To view the locked main-result dashboard:

```bash
python experiments/cross_domain/final_results_dashboard.py --port 8777
```

## Main Result Snapshot

Current strict main results:

| Metric | Naive | SA-MCGS |
|---|---:|---:|
| Root@3 | 48% | 81% |
| Risk-any | 72% | 98% |
| Risk-all | 47% | 78% |
| Compression | 67% | 53% |
| Method errors | 59/320 | 0/320 |

Interpretation: SA-MCGS is not framed as making Naive useless. The paper claim is that **SA-MCGS uses rollout search and structural evidence to more reliably retain risk endpoints and collapse cyclic dependency regions into interpretable risk subgraphs**, especially when full-SCC one-shot prompting becomes unstable.

## Current Goal: Risk Subgraph Extraction
Instead of just identifying a single "perpetrator" clause, the system focuses on extracting a **conflict/risk subgraph**: a compact subset of clauses and dependencies that explains why a structural risk exists and how it propagates.

## Core Algorithm: AlphaGo-style MCGS
The method uses an AlphaGo-style MCTS architecture for deep exploration of risk propagation:
- **UCB Selection with Dirichlet Noise**: Balances breadth and depth.
- **Transposition Table (TT)**: Reuses search results across paths to handle dense cyclic graphs.
- **Virtual Loss Parallelism**: Supports high-concurrency LLM evaluation.
- **Node/Edge Stats**: Tracks `risk_score` and `conflict_probability` to build the risk subgraph.

## Graph Pruning: NCP (Normative Core Pruning)
To handle massive legal graphs, **NCP** simplifies the search space without losing critical signal:

| Mode | Strategy | Principle |
| :--- | :--- | :--- |
| **Legacy** | Noise + Hierarchy + IB | **Heuristic-driven**: Removes hallucinations and hierarchy violations. Fast & Stable. |
| **Plan B** | Adaptive TACS | **Topology-driven**: Uses betweenness centrality to protect the "structural backbone" of SCCs when semantic types are homogeneous. High Accuracy. |

## Key Research Reports

- [**Main Experiment Lock**](experiments/main_experiment/README.md): canonical ARR/EMNLP main-result scope.
- [**Paper Supplements**](experiments/main_experiment/supplements/README.md): matched/valid-only, Naive output-burden, convergence, compression-profile, and prompt-rubric evidence.
- [**Final Experiment Plan**](experiments/cross_domain/plan.md): last-stage paper-writing priorities and reviewer-risk checklist.
- [**Pruning V2 Analysis**](docs/reports/Pruning_V2_Analysis.md): comparison of Plan A/B/C.
- [**Risk Subgraph Validation**](docs/reports/V1_V2_Combined_Ablation.md): early validation of risk-subgraph extraction.
- [**AlphaGo MCGS Design**](src/modules/alphago_mcgs.py): implementation of the MCTS-style core.

---

## Project Structure

```
experiments/
├── main_experiment/                  # Locked paper main experiment
│   ├── README.md
│   ├── MANIFEST.json
│   └── STATUS.md
└── cross_domain/
    ├── final_results_dashboard.py    # Main-result dashboard
    ├── run_cross_domain_battle.py    # Cross-domain battle runner
    ├── run_severity_grid.py          # Severity/profile experiment runner
    └── results/                      # Raw and aggregate experiment outputs
src/
├── modules/
│   ├── alphago_mcgs.py               # AlphaGo-style MCGS
│   ├── graph_pruning.py              # NCP pruning framework
│   ├── tarjan.py                     # SCC detection
│   └── online_conformal_mcgs.py      # Conformal risk control
├── models/
│   ├── search_tree.py                # MCTS node/edge/TT models
│   └── graph.py                      # Dependency graph models
paper/
└── latex/                            # ARR/EMNLP LaTeX writing workspace
docs/
└── reports/                          # Earlier analysis and validation reports
```

## Writing Rule

For the paper, main claims and tables should cite only `experiments/main_experiment/`. Anything else must be labeled as appendix, ablation, diagnostic, or exploratory.
