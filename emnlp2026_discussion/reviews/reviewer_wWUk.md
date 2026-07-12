# Official Review of Submission8229 by Reviewer wWUk

Date: 01 Jul 2026, 15:36  
Modified: 09 Jul 2026, 06:46  
Screenshots: `images/reviewer_wWUk_part1.png`, `images/reviewer_wWUk_part2.png`

## Paper Summary

This paper proposes SA-MCGS, a structure-aware Monte Carlo graph search framework for identifying and extracting compact risk subgraphs from strongly connected components (SCCs) in document graphs. The method combines SCC-localized LLM rollouts, relation-first evidence accumulation, and dynamic core compression to address the limitations of conventional TreeMCTS in cyclic reasoning settings. Experiments on four domains demonstrate substantial improvements in risk localization and evidence retention relative to a strong boosted full-SCC prompting baseline.

## Summary Of Strengths

- **Addresses an important and underexplored problem.** The paper focuses on cyclic document structures, a realistic challenge in legal, regulatory, and dependency-analysis settings that is largely overlooked by existing LLM reasoning work.
- **Strong technical motivation.** The discussion of path-copy explosion and state duplication in SCCs (Sec. 3.1, Eq. 1) clearly explains why standard TreeMCTS degrades in cyclic graphs and motivates SCC-aware reasoning.
- **Well-integrated framework.** The combination of SCC-localized rollouts, relation-first evidence memory (Eq. 6-7), online evidence accumulation, and dynamic core compression (Eq. 8) is conceptually coherent and easy to follow.
- **Strong empirical improvements.** SA-MCGS achieves large gains over the oracle-risk boosted baseline, including improvements in Root@3 (58%->81%), Risk-any (79%->98%), and Risk-all (62%->78%).
- **High reproducibility.** The paper includes detailed algorithms, prompt templates, benchmark construction details, coefficient tables, and extensive appendices.

## Summary Of Weaknesses

- **Evaluation relies primarily on injected risks.** While the audit study is helpful, most results are obtained on synthetic structural conflicts (Sec. 4.3). Demonstrating effectiveness on naturally occurring risks would strengthen the paper's practical significance such as expert-annotated contract review datasets such as CUAD and MAUD, contract inference datasets such as ContractNLI, large-scale real contract provision corpora such as LEDGAR, and unfair-clause detection datasets such as CLAUDETTE/UNFAIR-ToS, and so on.
- **Baseline comparisons are somewhat narrow.** The paper compares mainly against full-SCC prompting variants. Given recent work on graph-based document reasoning using contract graphs (Dechtiar et al., 2025) and legal GraphRAG frameworks that explicitly model cross-document relationships through knowledge graphs (Chen et al., 2026; de Martim, 2025), comparisons against representative document-graph reasoning systems would help clarify whether the observed gains arise from SCC-aware Monte Carlo search specifically or from leveraging structured graph representations more broadly.
- **Computational cost is insufficiently analyzed.** SA-MCGS performs many rollout-based LLM calls (Sec. 4.4), but the paper provides limited discussion of latency, token usage, and cost-performance tradeoffs, which are important for practical deployment. While authors mention the same as an afterthought in the limitations section, a more useful effort will be to study the costs and report them so that interested parties can make an informed choice if they want to use this.

## Comments Suggestions And Typos

As outlined in the weaknesses.

## Ratings And Metadata

Confidence: 3 = Pretty sure, but there's a chance I missed something. Although I have a good feel for this area in general, I did not carefully check the paper's details, e.g., the math or experimental design.

Soundness: 3.5

Excitement: 3 = Interesting: I might mention some points of this paper to others and/or attend its presentation in a conference if there's time.

Overall Assessment: 3 = Findings: I think this paper could be accepted to the Findings of the ACL.

Best Paper Justification:

NA

Limitations And Societal Impact:

Yes

Ethical Concerns:

There are no concerns with this submission

Needs Ethics Review: No

Reproducibility: 4 = They could mostly reproduce the results, but there may be some variation because of sample variance or minor variations in their interpretation of the protocol or method.

Datasets: 4 = Useful: I would recommend the new datasets to other researchers or developers for their ongoing work.

Software: 4 = Useful: I would recommend the new software to other researchers or developers for their ongoing work.

Knowledge Of Or Educated Guess At Author Identity: No

Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Knowledge Of Paper Source: N/A, I do not know anything about the paper from outside sources

Impact Of Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Reviewer Certification: I certify that the review I entered accurately reflects my assessment of the work. If you used any type of automated tool to help you craft your review, I hereby certify that its use was restricted to improving grammar and style, and the substance of the review is either my own work or the work of an acknowledged secondary reviewer.

Publication Ethics Policy Compliance: I did not use any generative AI tools for this review

