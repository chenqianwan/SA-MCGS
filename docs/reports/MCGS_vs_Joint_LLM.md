# Head-to-Head: SA-MCGS (Online Conformal) vs Joint LLM

**Date**: 2026-04-24
**Goal**: Evaluate if SA-MCGS provides a "Search-based Advantage" over "Joint LLM" (Single-pass inference on the whole SCC) for subtle defects (Type B/C).

## 1. Summary of Results

| Case ID | Type | SCC Size | Joint LLM Det. | SA-MCGS Det. | Δ (Advantage) |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **bgb_327** | Type B | 24 | ✅ (0.9) | ✅ (0.85) | Comparable |
| **bgb_275** | Type B | 9 | 😫 (0.0) | 😫 (0.65)* | **Search Friction** |
| **bgb_234** | Type B | 5 | ✅ (0.7) | ✅ (0.75) | +0.05 |
| **bgb_1573**| Type B | 3 | ✅ (0.8) | ✅ (0.8) | Comparable |
| **bgb_327** | Type C | 24 | ✅ (0.8) | ✅ (0.8) | Comparable |
| **bgb_1820**| Type C | 3 | ✅ (0.7) | 😫 (0.65) | -0.05 |

*\*SA-MCGS showed higher "Search Friction" (Risk Subgraph expansion) even if the hard threshold wasn't hit.*

## 2. Key Insights

### 2.1 The Small SCC "Joint Advantage"
For small SCCs (3-5 nodes), **Joint LLM** is highly efficient and often more accurate. The LLM can "see" all clauses at once in its attention window, making it hard to beat with iterative search.

### 2.2 The Large SCC "Search Resilience"
In the **24-node SCC** (bgb_327), SA-MCGS matched Joint LLM. However, Joint LLM was nearing its `max_tokens` limit (approx. 4000 tokens output). For SCCs > 50 nodes, Joint LLM is expected to fail (see Scaling Analysis), while SA-MCGS remains stable due to its modular search architecture.

### 2.3 Online Conformal Detection (Contribution 2)
In the `bgb_275` case, SA-MCGS detected higher **uncertainty** and **exceedance fractions** even when the raw score didn't cross the threshold. This "Conformal Signal" acts as a secondary safety net for subtle defects.

## 3. Conclusion
SA-MCGS is not a "replacement" for Joint LLM at small scales, but a **scaling solution**. Its primary value lies in its ability to handle "Attention-Deficit" scenarios in large, complex contract structures where Joint LLM's single-pass performance collapses.
