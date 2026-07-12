# Official Review of Submission8229 by Reviewer rxvy

Date: 02 Jul 2026, 14:31  
Modified: 09 Jul 2026, 06:46  
Screenshots: `images/reviewer_rxvy_part1.png`, `images/reviewer_rxvy_part2.png`

## Paper Summary

This paper studies risk extraction from cyclic document graphs, where the relevant evidence is distributed across mutually dependent records rather than contained in a single suspicious paragraph. The motivating examples include contracts, statutes, software package metadata, and corporate disclosure records. In these settings, a risk may only become visible after following directed dependencies among records, especially inside strongly connected components where records can refer back to one another. The paper proposes SA-MCGS, a structure-aware Monte Carlo graph search method for extracting compact risk subgraphs from cyclic document regions. The method first identifies strongly connected components, then performs local LLM-guided rollouts within each component. Unlike ordinary tree-based MCTS, which can repeatedly expand path copies of the same physical record in a cycle, SA-MCGS stores evidence by physical nodes and relations. It maintains relation-first evidence memory, uses SCC-aware UCB-style selection, revisits critical pairs, and collapses the cyclic region into a dynamic risk core.

## Summary Of Strengths

The paper addresses a concrete and underexplored problem: extracting risk-relevant evidence from cyclic document graphs. This is a useful setting for ACL because many document reasoning tasks involve cross-references, dependencies, clauses, definitions, and exceptions, where the key evidence is relational rather than localized in a single span. The proposed method is well motivated. The paper clearly explains why ordinary tree-style rollouts are poorly suited to strongly connected components: the same physical record can be revisited through many path copies, causing budget dilution and unstable value estimates. SA-MCGS directly targets this issue by localizing SCCs, using local LLM rollouts, storing evidence by physical nodes and relations, and collapsing the component into a compact dynamic risk core.

A strength of the work is that the output is not just a binary risk label. The method returns a risk subgraph intended to preserve repair-relevant endpoints. This makes the task more realistic for legal, regulatory, and technical document review, where a user needs to see both sides of a conflict rather than only a suspicious record.

## Summary Of Weaknesses

1. The main evaluation uses injected critical structural risks: existing records are edited to create a root and a distant witness that jointly form a conflict. This is useful for controlled evaluation, but it does not show that the method can detect naturally occurring risks in real document graphs. The expert audit supports that a small sample of injected risks is recognizable to qualified readers, but it does not validate that the benchmark distribution matches real legal, regulatory, or software-review risks. The paper should therefore weaken claims about real high-stakes risk extraction, or add evaluation on naturally occurring cases.
2. The Naive baseline must read the entire SCC and produce a global ranking plus a final risk subgraph in one generation. SA-MCGS, by contrast, asks the LLM for local node scores and relation evidence, then constructs the final core algorithmically. This makes the comparison partly about prompt decomposition and schema difficulty, not only about SCC-aware Monte Carlo graph search. The output reliability tables show that Naive has many unusable generations, especially in long CUAD components, while SA-MCGS has no such failures. This is an important confound. A fairer comparison would include a decomposed/local-window baseline with the same output schema but without relation-first memory, OC signals, or dynamic-core replacement.
3. The supplementary model-level breakdown shows that strong full-SCC models such as Gemini 2.5 Pro and DeepSeek-V3 already perform very well under the oracle-risk Naive baseline, and SA-MCGS is not consistently better for them. The overall improvement appears to be driven substantially by settings where the full-SCC baseline suffers from invalid outputs or poor endpoint retention, especially Qwen2.5-72B and CUAD. The paper should discuss this more directly, because the current headline result makes the method look uniformly superior across models.
4. SA-MCGS combines SCC localization, UCB-style seed selection, relation priors, critical-pair revisiting, online calibrated conflict signals, relation-first memory, and dynamic-core compression. The paper provides a small motivating TreeMCTS ablation, but it does not sufficiently isolate which components are responsible for the main gains. In particular, the paper should report ablations such as: no relation memory, no OC signal, no critical-pair ledger, monotone core instead of replacement core, random local-window selection, and local-window repeated prompting without graph search.

## Comments Suggestions And Typos

1. Please add clean or non-risk SCCs. Current metrics mainly measure whether injected endpoints are retained. A negative-case evaluation would show whether SA-MCGS over-reports risks.
2. The fixed prior coefficients should be accompanied by a sensitivity analysis. Since these weights affect rollout selection and core construction, it would be useful to know whether performance is stable under reasonable perturbations.
3. Minor writing suggestion: the term "oracle-risk Naive" is accurate but slightly confusing. Please define it once very explicitly as a boosted full-SCC baseline selected using ground-truth risk metrics, so readers do not mistake it for a deployable baseline.
4. Please report a subgraph precision or irrelevant-node rate. Compression alone does not tell whether the retained subgraph is clean or contains many distracting records.

## Ratings And Metadata

Confidence: 4 = Quite sure. I tried to check the important points carefully. It's unlikely, though conceivable, that I missed something that should affect my ratings.

Soundness: 2.5

Excitement: 3.5

Overall Assessment: 2.5 = Borderline Findings

Limitations And Societal Impact:

The paper discusses several important limitations, including the higher cost of SA-MCGS, the use of injected critical risks, the need for human audit on naturally occurring risks, and the dependence on graph construction quality. These are useful and honest limitations. However, the societal-impact discussion should be expanded. The method is framed for high-stakes legal, regulatory, financial, and software-dependency review. In these settings, false positives may create unnecessary review burden, while false negatives may hide contractual, compliance, or dependency risks. The authors should explicitly state that SA-MCGS should be used as a decision-support tool rather than as an automated risk adjudicator. They should also discuss the risk that graph-construction errors or injected-benchmark performance may lead users to overtrust the system on naturally occurring cases.

Ethical Concerns:

There are no concerns with this submission

Needs Ethics Review: No

Reproducibility: 3 = They could reproduce the results with some difficulty. The settings of parameters are underspecified or subjectively determined, and/or the training/evaluation data are not widely available.

Datasets: 3 = Potentially useful: Someone might find the new datasets useful for their work.

Software: 3 = Potentially useful: Someone might find the new software useful for their work.

Knowledge Of Or Educated Guess At Author Identity: No

Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Knowledge Of Paper Source: N/A, I do not know anything about the paper from outside sources

Impact Of Knowledge Of Paper: N/A, I do not know anything about the paper from outside sources

Reviewer Certification: I certify that the review I entered accurately reflects my assessment of the work. If you used any type of automated tool to help you craft your review, I hereby certify that its use was restricted to improving grammar and style, and the substance of the review is either my own work or the work of an acknowledged secondary reviewer.

Publication Ethics Policy Compliance: I did not use any generative AI tools for this review

