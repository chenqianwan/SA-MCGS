# SA-MCGS: Structure-Aware Monte Carlo Graph Search for Legal Risk Evaluation

## 🎯 Current Goal: Risk Subgraph Extraction
Instead of just identifying a single "perpetrator" clause, our system now focuses on extracting a **minimal conflict subgraph** — the smallest subset of clauses and dependencies that explain why a risk exists and how it propagates.

## 🧠 Core Algorithm: AlphaGo-style MCGS (Slow Thinking)
We have transitioned to a single-step "AlphaGo-style" MCTS architecture for deep exploration of risk propagation:
- **UCB Selection with Dirichlet Noise**: Balances breadth and depth.
- **Transposition Table (TT)**: Reuses search results across paths to handle dense cyclic graphs.
- **Virtual Loss Parallelism**: Supports high-concurrency LLM evaluation.
- **Node/Edge Stats**: Tracks `risk_score` and `conflict_probability` to build the risk subgraph.

## ✂️ Graph Pruning: NCP (Normative Core Pruning)
To handle massive legal graphs (e.g., QuantLaw), we use **NCP** to simplify the search space without losing critical signal:

| Mode | Strategy | Principle |
| :--- | :--- | :--- |
| **Legacy** | Noise + Hierarchy + IB | **Heuristic-driven**: Removes hallucinations and hierarchy violations. Fast & Stable. |
| **Plan B** | Adaptive TACS | **Topology-driven**: Uses betweenness centrality to protect the "structural backbone" of SCCs when semantic types are homogeneous. High Accuracy. |

## 📊 Key Research Reports
- [**Pruning V2 Analysis** (latest)](docs/reports/Pruning_V2_Analysis.md): Detailed comparison of Plan A/B/C. **Plan B identified as the most robust strategy.**
- [**Risk Subgraph Validation**](docs/reports/V1_V2_Combined_Ablation.md): Confirms 100% signal detection rate across 16 injection points (Type A/B/C).
- [**AlphaGo MCGS Design**](src/modules/alphago_mcgs.py): Technical implementation of the slow-thinking MCTS core.

---

## 🛠️ Project Structure (Latest)

```
src/
├── modules/
│   ├── alphago_mcgs.py   # AlphaGo-style MCTS (Slow Thinking) ⭐
│   ├── graph_pruning.py  # NCP Pruning Framework (Legacy / Plan B) ⭐
│   ├── tarjan.py         # SCC Detection
│   └── online_conformal_mcgs.py # Risk control via Conformal Prediction
├── models/
│   ├── search_tree.py    # MCTS Node/Edge/TT models
│   └── graph.py          # Dependency Graph models
experiments/
├── run_pruning_v2.py     # Latest 126-run parallel experiment script
└── perturbation.py       # Type A/B/C defect injection logic
docs/
└── reports/              # Scientific analysis and validation suites
```
