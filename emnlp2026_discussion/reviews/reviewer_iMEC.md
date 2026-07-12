# Official Review of Submission8229 by Reviewer iMEC

Date: 05 Jul 2026, 21:43  
Modified: 09 Jul 2026, 06:46  
Screenshot: `images/reviewer_iMEC.png`

## Paper Summary

This paper studies risk subgraph extraction in cyclic document graphs, where risks arise from relations among mutually dependent records. To address rollout instability caused by repeated revisits in strongly connected components (SCCs), the paper proposes SA-MCGS, a structure-aware Monte Carlo graph search method. The method localizes SCCs, performs local LLM rollouts with relation-first evidence memory, and collapses cyclic regions into compact risk subgraphs. The experiments on four document-graph domains suggest that SA-MCGS improves risk-root localization and repair-relevant evidence retention over an oracle-risk full-SCC Naive baseline.

## Summary Of Strengths

The paper identifies a concrete failure mode of applying tree-style LLM search to cyclic document graphs, where SCCs can lead to repeated revisits to the same logical records and inefficient rollout behavior.

SA-MCGS is designed around the structure of cyclic document graphs rather than relying on generic long-context prompting, combining SCC localization, local LLM rollouts, relation-first evidence memory, and dynamic core construction.

The paper provides a comprehensive analysis, including SCC-size effects, rollout-budget trends, output reliability, and results across different models and domains.

## Summary Of Weaknesses

The technical contribution seems not very significant. The contribution lies more in task-specific adaptation and integration of existing methods, such as graph search and subgraph compression.

Current ablation studies mainly diagnose the failure of TreeMCTS in SCCs, but component-level ablations for SA-MCGS itself are insufficient.

Practical inference cost is not sufficiently characterized and evaluated. Token-budget comparability is only briefly mentioned, without a detailed experimental cost comparison.

SA-MCGS does not consistently outperform the baseline across all models. It seems that on DeepSeek-V3 and Gemini 2.5 Pro, it achieves lower performance than oracle-risk Naive.

## Comments Suggestions And Typos

The paper may need to add component-level ablations for the key SA-MCGS modules, and report actual inference costs, including input/output tokens, number of calls, and runtime.

The paper may also need to include simpler graph-aware baselines, such as k-hop neighborhood scoring or local-window evidence aggregation.

"Appendix 9 separates..." appears to be a typo and should likely be "Appendix J separates..."?

## Ratings And Metadata

Confidence: 3 = Pretty sure, but there's a chance I missed something. Although I have a good feel for this area in general, I did not carefully check the paper's details, e.g., the math or experimental design.

Soundness: 3 = Acceptable: This study provides sufficient support for its main claims. Some minor points may need extra support or details.

Excitement: 3 = Interesting: I might mention some points of this paper to others and/or attend its presentation in a conference if there's time.

Overall Assessment: 2.5 = Borderline Findings

Ethical Concerns:

There are no concerns with this submission

Reproducibility: 3 = They could reproduce the results with some difficulty. The settings of parameters are underspecified or subjectively determined, and/or the training/evaluation data are not widely available.

Datasets: 1 = No usable datasets submitted.

Software: 1 = No usable software released.

Knowledge Of Or Educated Guess At Author Identity: No

Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Knowledge Of Paper Source: N/A, I do not know anything about the paper from outside sources

Impact Of Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Reviewer Certification: I certify that the review I entered accurately reflects my assessment of the work. If you used any type of automated tool to help you craft your review, I hereby certify that its use was restricted to improving grammar and style, and the substance of the review is either my own work or the work of an acknowledged secondary reviewer.

Publication Ethics Policy Compliance: I used a privacy-preserving tool exclusively for the use case(s) approved by PEC policy, such as language edits

