# Contribution 1: Risk Subgraph Tracking via SA-MCGS

## 1. Motivation: The "Cyclic Blind Spot"
Traditional LLM-based legal analysis suffers from two primary limitations in complex contracts:
1.  **Linear Bias**: LLMs tend to process text sequentially, often missing long-range dependencies that loop back (Circular Dependencies).
2.  **SCC Complexity**: In a Strongly Connected Component (SCC), a single defect in Clause A can propagate to Clause B, which then affects Clause C, eventually looping back to A. This creates a logical "hallucination trap" for standard prompting.

**SA-MCGS (Structure-Aware Monte Carlo Graph Search)** was designed to systematically explore these cycles.

---

## 2. Core Mechanism: "Slow Thinking" Search
Inspired by AlphaGo, we implement a search-based evaluation instead of a single-pass inference:

### A. Deep Path Exploration
- **UCB Selection**: Uses the Upper Confidence Bound to prioritize unexplored "risky" branches.
- **Transposition Table (TT)**: Crucial for cyclic graphs. It ensures that if the search reaches the same clause via a different path in the cycle, it reuses the accumulated risk statistics instead of re-evaluating, preventing infinite loops and saving costs.

### B. Risk Value Function
- Each node evaluation yields a `risk_score` (0-1) and a `reasoning`.
- The system aggregates these into a **Conflict Probability Matrix**, mapping which edges are most likely to transmit "normative tension."

---

## 3. The "Magnifier" Effect: OC vs. Subgraph Expansion
One of our key findings is the difference between "Alarming" and "Understanding":

- **OC Detection (Alarming)**: Direct identification of a defect. Often misses subtle "Type C" (Scope Expansion) defects because the signal is weak.
- **Subgraph Expansion (Understanding)**: When a defect is injected, even if the LLM doesn't explicitly "alarm," the search tree **expands significantly** in that region as the LLM encounters more logical friction.

**Result**: For Type C defects, while OC detection was only ~0.8, the **Risk Subgraph expanded by 8.4 nodes (300%+)**, acting as a powerful magnifier for hidden risks.

---

## 4. Empirical Validation (Summary of V1+V2)
- **100% Signal Detection (V1)**: Every injected defect (Type A, B, and C) was successfully captured as a statistical anomaly in the search tree.
- **81% Localization (V2)**: The extracted minimal conflict subgraph successfully included the "Perpetrator" node or its immediate neighbor in 81% of cases, without needing a "Clean" baseline (Closed-book).

---

## 5. Implementation Reference
- **Core Engine**: `src/modules/alphago_mcgs.py`
- **Stats Model**: `src/models/search_tree.py`
- **Validation Suite**: `experiments/run_v1_v2_combined.py`
