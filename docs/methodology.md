# SA-MCGS Methodology: Structure-Aware Monte Carlo Graph Search

SA-MCGS is a framework for legal risk evaluation that combines topological graph analysis with Monte Carlo Tree Search (MCTS) and Online Conformal Prediction.

## 1. System Architecture

The pipeline consists of 8 core steps:

1.  **Clause Segmentation**: Parsing raw contract text into atomic clauses.
2.  **Graph Construction**: Extracting semantic dependencies (Defines, Constrains, Triggers, Modifies, References).
3.  **Plugin-Based Pruning (New)**: 
    - **Legacy**: Noise Removal, Hierarchical Priors, Information Bottleneck.
    - **Adaptive TACS**: Type-Aware Cycle Saliency with topological fallback.
4.  **SCC Detection**: Identifying Strongly Connected Components (logical loops).
5.  **DAG Evaluation**: Deterministic pass for acyclic parts.
6.  **SCC Sampling**: Multiple LLM-based joint evaluations for the "collapsed" SCC.
7.  **MCGS Search (AlphaGo Style)**:
    - **UCB1 Selection**: Exploration-exploitation balance.
    - **Transposition Table**: Efficient reuse of cyclic evaluations.
8.  **Online Conformal Prediction**: Statistical self-calibration and outlier detection for risk identification.

## 2. Key Contributions

### Contribution 1: Risk Subgraph Tracking (MCTS)
Instead of a single score, SA-MCGS identifies a "minimal conflict subgraph" that explains the origin and propagation of risk through cycles.

### Contribution 2: Online Conformal Prediction
We apply Online Conformal Prediction (e.g., Gibbs & Candes, 2021) to dynamically calibrate risk thresholds. This allows the system to detect subtle anomalies (Type B/C) that standard threshold-based methods miss.

### Contribution 3: Domain-Informed Pruning
Two-layer pruning reduces search space by up to 75%:
- **Layer 1 (Heuristic)**: Cleans noise and enforces legal logic.
- **Layer 2 (Semantic-Topological)**: Decomposes complex SCCs based on semantic saliency or betweenness centrality.

## 3. Data Sources
- **QuantLaw**: Statutory and regulatory cross-reference graphs (US/DE).
- **CUAD**: Commercial contract dataset with annotated clauses.
- **BGB (German Civil Code)**: Case study for complex, multi-scale SCCs.
