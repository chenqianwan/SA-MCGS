# Scaling Analysis: LLM Memory & Reasoning Tipping Points

**Date**: 2026-04-24
**Focus**: Investigating the degradation of LLM performance as the number of clauses (context window and logic depth) increases.

## 1. Experimental Setup
- **Baseline**: DeepSeek-chat (8k context, compact prompt).
- **Injection Types**: 
  - **Type A**: Semantic Contradiction (Obvious).
  - **Type C**: Subtle Scope Expansion (Stealthy).
- **Scales**: 5, 10, 20, 30, 50, 60, 80, 100, 120, 150, 200, 300, 500 clauses.
- **Metrics**: Detection Rate, Average Score, JSON Failure Rate (output truncation).

## 2. Core Findings

### 2.1 The "Tipping Point" (60-100 Clauses)
For **Type A** (Obvious) defects:
- **0-60 Clauses**: 100% Stability. The LLM perfectly identifies direct semantic contradictions.
- **80-100 Clauses**: First signs of "Attention Fragmentation." Detection rate drops to **80%**. The model begins to miss contradictions when buried deep in the context.
- **150+ Clauses**: Catastrophic failure. Detection rate drops to **20%** at 200 clauses and **0%** at 300+ clauses.

### 2.2 Output Capacity Bottleneck (JSON Failures)
As the number of clauses increases, the requirement for the LLM to provide a structured JSON evaluation for each clause leads to `max_tokens` overflow:
- **Scale 100**: 20% JSON Failure rate.
- **Scale 200**: 80% JSON Failure rate.
- **Scale 300+**: 100% Failure rate.
Even with `max_tokens: 8192` and `compact` prompts, the "Joint LLM" approach fails to return full results for large SCCs.

### 2.3 The "Stealthy" Type C Barrier
- **Type C** (Subtle) detection peaks at **40%** for Scale=20.
- Beyond 30 clauses, the LLM's "Natural Language Inference" (NLI) capability for subtle scope expansions hits a floor of **0%**.
- This justifies the need for **SA-MCGS**, which breaks down the large context into smaller, manageable "search rollouts."

## 3. Comparative Visualization (Conceptual)

| Scale (Clauses) | Type A Det. | Type C Det. | JSON Stability | Verdict |
| :--- | :---: | :---: | :---: | :--- |
| 5 - 50 | 100% | 0-40% | High | LLM Optimal |
| 60 - 80 | 100-80% | 0% | Medium | Tipping Point |
| 100 - 150 | 80-60% | 0% | Low | Failure Imminent |
| 200+ | 20-0% | 0% | Critical | **SA-MCGS Mandatory** |

## 4. Conclusion
Direct LLM evaluation ("Joint LLM") has a hard limit around **60-80 clauses** in legal reasoning tasks. Beyond this, both memory (missing contradictions) and output capacity (JSON truncation) render the "brute force" approach unfeasible. SA-MCGS circumvents this by using a graph-based search that maintains local context efficiency regardless of global scale.
