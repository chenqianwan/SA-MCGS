# ACL Sentence-Level Editing Notes, v2

Source reviewed: `paper/latex/acl_latex.tex`.

Scope: I reviewed the paper sentence by sentence and list only revisions that I would make for ACL-level style, clarity, or abbreviation hygiene. The main goal is sentence-level polishing, not term expansion. Term-expansion edits are marked `[TERM]`; those are the only places where the replacement may become noticeably longer.

Style constraints used here:

- Use American English.
- Avoid frequent conversational pivots such as `but` and `rather than`.
- Prefer `instead of`, `although`, `whereas`, `while`, or direct contrast when they fit.
- Reduce colon and semicolon density where it makes the prose feel explanatory or informal.
- Avoid several consecutive sentences starting with `A`, `The`, `It`, or `This`.
- Keep replacements about the same length, except where first-use abbreviations require full names.

## Main Text

### Line 55 `[TERM]`
- Current: `LLM-guided Monte Carlo tree search (MCTS) can improve structured document reasoning, but standard tree rollouts become unstable on strongly connected components (SCCs), where the same logical record may be revisited indefinitely.`
- Issue: `LLM` appears before its full form, and `but` weakens the formal contrast.
- Replace with: `Monte Carlo tree search (MCTS) guided by large language models (LLMs) can improve structured document reasoning, whereas standard tree rollouts become unstable on strongly connected components (SCCs), where the same logical record may be revisited indefinitely.`

### Line 55
- Current: `We propose \samcgs{}, a structure-aware Monte Carlo graph search method that localizes SCCs, performs local LLM rollouts with relation-first evidence memory, and collapses each cyclic region into an inspectable risk subgraph.`
- Issue: After the first-use expansion, use macros or consistent abbreviations rather than raw `SCCs` and `LLM`.
- Replace with: `We propose \samcgs{}, a structure-aware Monte Carlo graph search method that localizes \scc{}s, performs local LLM rollouts with relation-first evidence memory, and collapses each cyclic region into an inspectable risk subgraph.`

### Line 55 `[TERM]`
- Current: `We evaluate a locked critical structural benchmark covering four authority-backed domains: Debian dependencies, SEC EX-21 subsidiary disclosures, German Civil Code cross-references, and CUAD contracts.`
- Issue: `SEC EX-21` and `CUAD` need full forms on first mention; the colon is also heavier than needed in the abstract.
- Replace with: `We evaluate a locked critical structural benchmark across four authority-backed domains, covering Debian dependencies, U.S. Securities and Exchange Commission Exhibit 21 (SEC EX-21) subsidiary disclosures, German Civil Code cross-references, and Contract Understanding Atticus Dataset (CUAD) contracts.`

### Line 55
- Current: `The gains are larger under long-context pressure, while the returned subgraphs retain complete critical evidence and remove more than half of the original SCC nodes.`
- Issue: `complete critical evidence` is slightly vague, and `while` makes the sentence carry two claims loosely.
- Replace with: `The gains are larger under long-context pressure, and the returned subgraphs retain core evidence while removing more than half of the original SCC nodes.`

### Line 61
- Current: `Many high-stakes document analysis tasks are graph problems hidden inside text.`
- Issue: `hidden inside text` is vivid but a little informal for ACL prose.
- Replace with: `Many high-stakes document analysis tasks are graph problems expressed in text.`

### Line 61
- Current: `Each record can look plausible in isolation; the risk appears only when the directed dependencies among records are followed.`
- Issue: The semicolon is unnecessary, and the contrast reads more cleanly as subordination.
- Replace with: `Although each record can look plausible in isolation, the risk appears only when the directed dependencies among records are followed.`

### Line 63
- Current: `Large language models (LLMs) can read long contexts, but nominal context length does not guarantee reliable retrieval, multi-hop tracing, or aggregation under long inputs.`
- Issue: The contrast is central, so use a more formal connector than `but`.
- Replace with: `Large language models (LLMs) can read long contexts, yet nominal context length does not guarantee reliable retrieval, multi-hop tracing, or aggregation under long inputs.`

### Line 63
- Current: `The failure mode we study is sharper: \emph{cyclic} document regions, where evidence is revisitable and diffuse.`
- Issue: The sentence is colon-heavy and slightly vague.
- Replace with: `We study a sharper failure mode in \emph{cyclic} document regions, where evidence is revisitable and diffuse.`

### Lines 65-68
- Current: `One might try to escape one-shot prompting by using AlphaGo-style search. Nevertheless, ordinary MCTS is naturally a tree-unrolling procedure: in a loopy graph, the search state grows with walk prefixes as opposed to physical records.`
- Issue: `One might try` sounds conversational, `Nevertheless` is heavy, and `as opposed to` is awkward.
- Replace with: `A natural alternative is AlphaGo-style search. However, ordinary MCTS unrolls trajectories as trees: in a loopy graph, the search state grows with walk prefixes instead of physical records.`

### Lines 76-79
- Current: `Neither line provides a mechanism for turning a strongly connected document region itself into a stable and reliable evaluation unit. Our setting instead requires localizing the \scc{} and collapsing it into an evidence-preserving risk subgraph, showing more detail in risk source and evidence.`
- Issue: `showing more detail in risk source and evidence` is unidiomatic.
- Replace with: `Neither line provides a mechanism for turning a strongly connected document region itself into a stable evaluation unit. Our setting instead requires localizing the \scc{} and collapsing it into an evidence-preserving risk subgraph with explicit source and evidence.`

### Line 81
- Current: `\samcgs{} goal is finding \scc{} bottlenecks at first, then performs local window rollouts inside each \scc{}.`
- Issue: Ungrammatical subject and verb structure.
- Replace with: `\samcgs{} first finds \scc{} bottlenecks and then performs local window rollouts inside each \scc{}.`

### Line 81
- Current: `Instead of treating risk as an intrinsic property of a single node, it stores relation-first evidence: a node becomes risky when earlier evidence makes its constraint, exception, or handoff incompatible with the graph context.`
- Issue: Good idea, but the colon makes the sentence explanatory and long.
- Replace with: `Instead of treating risk as intrinsic to one node, it stores relation-first evidence, where a node becomes risky when earlier evidence makes its constraint, exception, or handoff incompatible with the graph context.`

### Line 85
- Current: `given an \scc{} in a document graph, output a compact subgraph that retains the repair-relevant evidence endpoints, in place of single anomalous node.`
- Issue: Missing article and slightly awkward `in place of`.
- Replace with: `given an \scc{} in a document graph, output a compact subgraph that retains the repair-relevant evidence endpoints instead of a single anomalous node.`

### Line 86 `[TERM]`
- Current: `Its rollout policy uses UCB selection augmented with progressive relation priors, critical-pair revisiting, and evidence-gated core pruning.`
- Issue: `UCB` first appears here and should be expanded once.
- Replace with: `Its rollout policy uses upper confidence bound (UCB) selection augmented with progressive relation priors, critical-pair revisiting, and evidence-gated core pruning.`

### Line 86
- Current: `so additional search budget is routed toward relations that repeatedly look repair-relevant rather than toward arbitrary path copies.`
- Issue: `rather than toward` is wordy.
- Replace with: `so additional search budget is routed toward repeatedly repair-relevant relations, not arbitrary path copies.`

### Line 87 `[TERM]`
- Current: `Debian provides package-dependency graphs; SEC EX-21 provides subsidiary-disclosure graphs; BGB provides statutory cross-reference graphs; CUAD provides contract-clause graphs.`
- Issue: Repeated semicolons make the contribution list choppy; `BGB` also needs its full form on first mention if not already expanded in text.
- Replace with: `Debian provides package-dependency graphs, SEC EX-21 provides subsidiary-disclosure graphs, the German Civil Code (BGB) provides statutory cross-reference graphs, and CUAD provides contract-clause graphs.`

### Line 93
- Current: `\samcgs{} pipeline: SCC localization, local rollouts, relation-first evidence memory, and dynamic-core collapse.`
- Issue: Figure caption uses raw `SCC` and a colon where a noun phrase is enough.
- Replace with: `\samcgs{} pipeline for \scc{} localization, local rollouts, relation-first evidence memory, and dynamic-core collapse.`

### Line 72
- Current: `AlphaZero-style search by sharing states in a DAG-like search graph`
- Issue: `DAG` appears before the paper expands it. Avoiding the acronym here keeps the sentence short.
- Replace with: `AlphaZero-style search by sharing states in an acyclic search graph`

### Line 104
- Current: `We study risks that arise from relations, not merely from suspicious wording.`
- Issue: `not merely` is slightly rhetorical.
- Replace with: `We study relational risks, not risks signaled only by suspicious wording.`

### Line 104
- Current: `In the benchmark, an injected critical case modifies existing records only; no new nodes are added.`
- Issue: The semicolon is unnecessary.
- Replace with: `In the benchmark, an injected critical case modifies only existing records. No new nodes are added.`

### Line 111
- Current: `This is strict but important for critical risks because remediation often requires seeing both sides of the contradiction.`
- Issue: `strict but important` is conversational.
- Replace with: `This criterion is strict because remediation often requires seeing both sides of the contradiction.`

### Line 112
- Current: `Compression: $1-|H|/|S|$, reported higher-is-smaller.`
- Issue: `reported higher-is-smaller` is hard to parse.
- Replace with: `Compression: $1-|H|/|S|$, where higher values indicate smaller subgraphs.`

### Line 122 `[TERM]`
- Current: `In a directed acyclic graph this is acceptable: rollouts eventually terminate and backpropagation updates a finite set of states.`
- Issue: First-use `DAG` should be explicit, and the colon can be avoided.
- Replace with: `In a directed acyclic graph (DAG), this is acceptable because rollouts eventually terminate and backpropagation updates a finite set of states.`

### Line 127
- Current: `This causes search-tree expansion, rollout truncation, and value dilution.`
- Issue: `causes search-tree expansion` is less precise than `inflates`.
- Replace with: `This inflates the search tree, truncates rollouts, and dilutes value estimates.`

### Line 129
- Current: `The issue is not merely that a cycle exists; it is that tree expansion treats revisits as new path states.`
- Issue: Semicolon and `not merely` make the contrast feel overexplained.
- Replace with: `The issue is not only that a cycle exists. Tree expansion also treats revisits as new path states.`

### Line 134
- Current: `Why vanilla TreeMCTS is a poor primitive for SCCs: cyclic records create path-copy states, dilute rollout budget, and flatten value estimates.`
- Issue: `poor primitive` is strong and slightly informal; raw `SCCs` should be consistent with macros.
- Replace with: `Why vanilla TreeMCTS is ill-suited to \scc{}s: cyclic records create path-copy states, dilute rollout budget, and flatten value estimates.`

### Line 138
- Current: `The ablation is intentionally small and diagnostic; its role is not to establish the final benchmark result, but to test whether SCC topology breaks the assumptions that make tree search attractive in DAG-like document graphs.`
- Issue: The sentence sounds defensive and uses a semicolon plus `but`.
- Replace with: `The ablation is intentionally small and diagnostic. It tests whether \scc{} topology breaks the assumptions that make tree search attractive in DAG-like document graphs.`

### Line 158
- Current: `Table~\ref{tab:mcts_scc} tests the predicted failure directly: inside an \scc{}, TreeMCTS expands many more path-copy states, truncates every rollout, and produces flatter value estimates.`
- Issue: The colon is avoidable.
- Replace with: `Table~\ref{tab:mcts_scc} directly tests the predicted failure. Inside an \scc{}, TreeMCTS expands many more path-copy states, truncates every rollout, and produces flatter value estimates.`

### Line 167
- Current: `This formulation makes clear why compression alone is insufficient: a small $H$ is useful only if it retains repair-relevant evidence.`
- Issue: Colon-heavy phrasing.
- Replace with: `This formulation shows why compression alone is insufficient, since a small $H$ is useful only if it retains repair-relevant evidence.`

### Line 171
- Current: `DAG regions are handled by the ordinary upstream search, whereas each non-trivial \scc{} is processed by \samcgs{}.`
- Issue: After first-use expansion, use a consistent abbreviation form.
- Replace with: `Directed acyclic regions are handled by the ordinary upstream search, whereas each non-trivial \scc{} is processed by \samcgs{}.`

### Line 177
- Current: `Seed selection and frontier expansion follow the UCB intuition used in MCTS, but statistics are keyed by physical graph objects rather than path copies.`
- Issue: `but` plus `rather than` can be tightened.
- Replace with: `Seed selection and frontier expansion follow the UCB intuition used in MCTS, although statistics are keyed by physical graph objects instead of path copies.`

### Line 188
- Current: `The prior is computed from rollout evidence rather than from domain-specific labels:`
- Issue: `rather than from` is wordy, and the colon is unnecessary before the equation.
- Replace with: `The prior is computed from rollout evidence instead of domain-specific labels.`

### Line 195
- Current: `while keeping the update key tied to physical nodes and edges rather than path prefixes.`
- Issue: Replace the repeated `rather than` pattern.
- Replace with: `while keeping the update key tied to physical nodes and edges instead of path prefixes.`

### Line 199
- Current: `Structural risk is relational: a node can be harmless until previous evidence makes it incompatible with the graph context.`
- Issue: The colon makes a slogan-like sentence.
- Replace with: `Structural risk is relational because a node can be harmless until previous evidence makes it incompatible with the graph context.`

### Line 203
- Current: `Node evidence is updated by running averages and relation evidence by smoothed pair support; Appendix~\ref{sec:appendix_formula_details} gives the exact update equations.`
- Issue: The semicolon can be a period.
- Replace with: `Node evidence is updated by running averages and relation evidence by smoothed pair support. Appendix~\ref{sec:appendix_formula_details} gives the exact update equations.`

### Line 213
- Current: `Thus a node can become important because earlier or later evidence repeatedly implicates it, even if its isolated text is not obviously defective.`
- Issue: `earlier or later evidence` is imprecise.
- Replace with: `Thus a node can become important because incoming or outgoing evidence repeatedly implicates it, even if its isolated text is not obviously defective.`

### Line 213
- Current: `The \oc{} and pair-ledger terms are bounded bonuses: they route search toward severe recurring hypotheses, but do not let a single local judgment dominate persistent node or relation evidence.`
- Issue: Colon plus `but` make the sentence feel informal.
- Replace with: `The \oc{} and pair-ledger terms are bounded bonuses that route search toward severe recurring hypotheses without letting a single local judgment dominate persistent node or relation evidence.`

### Line 217
- Current: `At each rollout, \samcgs{} compares the strongest local relation-conflict score against an online quantile of previous conflict scores; Appendix~\ref{sec:appendix_formula_details} gives the exact rule.`
- Issue: Semicolon can be a period.
- Replace with: `At each rollout, \samcgs{} compares the strongest local relation-conflict score against an online quantile of previous conflict scores. Appendix~\ref{sec:appendix_formula_details} gives the exact rule.`

### Line 217 `[TERM]`
- Current: `We call a threshold crossing an online calibrated conflict signal, abbreviated \oc{}: it indicates that the current local window contains an unusually strong ordered-cycle or contradiction cue relative to earlier rollouts.`
- Issue: First-use abbreviation should use the standard full-name pattern; the colon can be removed.
- Replace with: `We call a threshold crossing an online calibrated conflict signal (\oc{}), which indicates that the current local window contains an unusually strong ordered-cycle or contradiction cue relative to earlier rollouts.`

### Line 217
- Current: `This follows the spirit of conformal calibration, but we do not claim formal coverage because the LLM evaluator and rollout policy are adaptive.`
- Issue: `but` can be replaced with a more formal concessive connector.
- Replace with: `This follows the spirit of conformal calibration, although we do not claim formal coverage because the LLM evaluator and rollout policy are adaptive.`

### Line 222
- Current: `The final risk subgraph is maintained as a dynamic core with replacement, avoiding monotonic expansion.`
- Issue: The participial phrase is slightly loose.
- Replace with: `The final risk subgraph is maintained as a dynamic core with replacement to avoid monotonic expansion.`

### Line 222
- Current: `The compression step is a budgeted subset-selection problem; greedy selection is a standard approximation strategy for monotone submodular objectives under cardinality constraints.`
- Issue: Semicolon can be a period.
- Replace with: `The compression step is a budgeted subset-selection problem. Greedy selection is a standard approximation strategy for monotone submodular objectives under cardinality constraints.`

### Line 234
- Current: `When a rollout observes both endpoints of a severe contradiction, subsequent rollouts should revisit and stabilize that relation, instead of allowing unrelated high-scoring distractors to occupy the subgraph.`
- Issue: The comma before `instead of` is unnecessary.
- Replace with: `When a rollout observes both endpoints of a severe contradiction, subsequent rollouts should revisit and stabilize that relation instead of allowing unrelated high-scoring distractors to occupy the subgraph.`

### Lines 263-267
- Current: `The dynamic core cap $B(S)$ bounds the retained subgraph, so additional budget refines the same physical memory rather than expanding a cyclic tree indefinitely. This yields an anytime collapsed evaluation point for higher-level graph search; budget-prefix behavior is analyzed in Figure~\ref{fig:convergence} and Appendix~\ref{app:diagnostics}.`
- Issue: Replace `rather than` and remove the semicolon.
- Replace with: `The dynamic core cap $B(S)$ bounds the retained subgraph, so additional budget refines the same physical memory instead of expanding a cyclic tree indefinitely. This yields an anytime collapsed evaluation point for higher-level graph search. Budget-prefix behavior is analyzed in Figure~\ref{fig:convergence} and Appendix~\ref{app:diagnostics}.`

### Line 275
- Current: `We evaluate on four domains chosen for structural diversity and source authority, not for result cherry-picking.`
- Issue: `cherry-picking` is conversational and reviewer-sensitive.
- Replace with: `We evaluate on four domains chosen for structural diversity and source authority, not to favor a particular result.`

### Line 296
- Current: `The four sources differ in surface form: a Debian record exposes package fields, a BGB record is a statutory section, an SEC EX-21 record is a subsidiary disclosure, and a CUAD record is a contract clause.`
- Issue: The colon is unnecessary.
- Replace with: `The four sources differ in surface form. A Debian record exposes package fields, a BGB record is a statutory section, an SEC EX-21 record is a subsidiary disclosure, and a CUAD record is a contract clause.`

### Line 300
- Current: `Both \naive{} and \samcgs{} use the same domain-neutral risk rubric: identify structural inconsistency, mutual incompatibility, underspecification, or high-impact risk from visible node text and visible directed edges.`
- Issue: Colon makes the rubric sound like prompt text.
- Replace with: `Both \naive{} and \samcgs{} use the same domain-neutral risk rubric, which asks models to identify structural inconsistency, mutual incompatibility, underspecification, or high-impact risk from visible node text and visible directed edges.`

### Line 300
- Current: `The difference is computational: full-\scc{} one-shot generation versus \scc{}-aware rollout selection, relation-first memory, critical-pair revisiting, and dynamic-core compression.`
- Issue: Colon-heavy contrast.
- Replace with: `The difference is computational, namely full-\scc{} one-shot generation versus \scc{}-aware rollout selection, relation-first memory, critical-pair revisiting, and dynamic-core compression.`

### Line 304
- Current: `The main experiment uses a locked critical-stress configuration over the same \scc{} blocks and models for both methods; the exact run profile is reported in Appendix~\ref{sec:appendix_experiments}.`
- Issue: Semicolon can be a period.
- Replace with: `The main experiment uses a locked critical-stress configuration over the same \scc{} blocks and models for both methods. The exact run profile is reported in Appendix~\ref{sec:appendix_experiments}.`

### Line 308
- Current: `We compare against a full-context direct-subgraph baseline: \naive{} sees the full \scc{} in one prompt and is asked to output both a whole-\scc{} risk ranking and a risk subgraph.`
- Issue: Avoid colon-led explanation.
- Replace with: `We compare against a full-context direct-subgraph baseline in which \naive{} sees the full \scc{} in one prompt and outputs both a whole-\scc{} risk ranking and a risk subgraph.`

### Line 308
- Current: `Thus \naive{} has more context per call but carries a heavier one-shot output burden, while \samcgs{} trades this for iterative search and evidence retention.`
- Issue: `but` and `while` stack two contrasts in one sentence.
- Replace with: `Thus \naive{} has more context per call and carries a heavier one-shot output burden, whereas \samcgs{} trades this for iterative search and evidence retention.`

### Line 310
- Current: `We evaluate four models: GPT-4o, DeepSeek-V3, Qwen2.5-72B-Instruct, and Gemini 2.5 Pro.`
- Issue: The colon is acceptable, but the paper already has high colon density. This one can be smoothed.
- Replace with: `We evaluate GPT-4o, DeepSeek-V3, Qwen2.5-72B-Instruct, and Gemini 2.5 Pro.`

### Line 318
- Current: `Panel A reports strict headline metrics; Panel B gives a compact \scc{}-size breakdown of endpoint retention and compression. Compression is higher-is-smaller and therefore shows the cost of retaining more evidence.`
- Issue: Semicolon and `higher-is-smaller` phrasing.
- Replace with: `Panel A reports strict headline metrics, and Panel B gives a compact \scc{}-size breakdown of endpoint retention and compression. Higher compression values indicate smaller subgraphs and show the cost of retaining more evidence.`

### Line 322
- Current: `The strongest claim is not that one-shot LLMs never find risk; the \naive{} baseline often finds at least one suspicious record.`
- Issue: Semicolon makes the sentence feel defensive.
- Replace with: `The strongest claim is not that one-shot LLMs never find risk. The \naive{} baseline often finds at least one suspicious record.`

### Line 324
- Current: `\naive{} returns smaller subgraphs on average, but it often drops one side of a critical contradiction or produces an output that is too large, incomplete, or otherwise unavailable for scoring.`
- Issue: `but` can be more formal.
- Replace with: `Although \naive{} returns smaller subgraphs on average, it often drops one side of a critical contradiction or produces an output that is too large, incomplete, or otherwise unavailable for scoring.`

### Line 330
- Current: `DeepSeek-V3 is already strong under \naive{} but still improves, and Gemini 2.5 Pro is competitive for both methods.`
- Issue: `but still improves` is slightly casual.
- Replace with: `DeepSeek-V3 is already strong under \naive{} and still improves, and Gemini 2.5 Pro is competitive for both methods.`

### Line 330
- Current: `Domain-wise, CUAD is the hardest setting because long contract text creates high output burden for full-\scc{} prompting; Debian and SEC are cleaner but still show endpoint-retention gains.`
- Issue: Semicolon and `but still` can be tightened.
- Replace with: `Domain-wise, CUAD is the hardest setting because long contract text creates high output burden for full-\scc{} prompting. Debian and SEC are cleaner and still show endpoint-retention gains.`

### Line 337
- Current: `This is consistent with the task: longer cycles contain more plausible distractors and more native ambiguity, especially in CUAD.`
- Issue: Avoid a repeated `This` opening and colon.
- Replace with: `The pattern is consistent with the task because longer cycles contain more plausible distractors and more native ambiguity, especially in CUAD.`

### Line 348
- Current: `Figure~\ref{fig:convergence} shows that additional rollouts do not merely spend more tokens; they accumulate useful evidence.`
- Issue: Semicolon and `do not merely` can be made more direct.
- Replace with: `Figure~\ref{fig:convergence} shows that additional rollouts accumulate useful evidence instead of only spending more tokens.`

### Line 348
- Current: `The final run-level \riskall{} in Figure~\ref{fig:main_metrics} is higher because the dynamic core uses the full retained evidence rather than a simple prefix truncation.`
- Issue: Replace repeated `rather than`.
- Replace with: `The final run-level \riskall{} in Figure~\ref{fig:main_metrics} is higher because the dynamic core uses the full retained evidence instead of a simple prefix truncation.`

### Line 352
- Current: `First, a more compressed profile reduces the average retained core from 7.69 to 5.91 nodes but lowers \riskall{} from 78\% to 71\%, so the main run keeps the profile that better preserves critical endpoints.`
- Issue: `but ... so` creates a long causal chain.
- Replace with: `First, a more compressed profile reduces the average retained core from 7.69 to 5.91 nodes and lowers \riskall{} from 78\% to 71\%, so the main run keeps the profile that better preserves critical endpoints.`

### Line 352
- Current: `Second, strict rates do not hide unavailable \naive{} outputs: on 261 matched usable pairs, \samcgs{} remains higher in \rootthree{} (83\% vs. 59\%), \riskany{} (98\% vs. 88\%), and \riskall{} (77\% vs. 57\%).`
- Issue: Colon-heavy structure.
- Replace with: `Second, strict rates do not hide unavailable \naive{} outputs. On 261 matched usable pairs, \samcgs{} remains higher in \rootthree{} (83\% vs. 59\%), \riskany{} (98\% vs. 88\%), and \riskall{} (77\% vs. 57\%).`

### Line 359
- Current: `Chain-of-thought prompting improves sequential reasoning, but cyclic document risk requires revisiting and reconciling records rather than extending one chain.`
- Issue: `but` plus `rather than` can be compressed.
- Replace with: `Chain-of-thought prompting improves sequential reasoning, whereas cyclic document risk requires revisiting and reconciling records instead of extending one chain.`

### Line 359
- Current: `Legal NLP benchmarks motivate document-level reasoning; our task stresses cyclic structural evidence retention.`
- Issue: Semicolon can be a period.
- Replace with: `Legal NLP benchmarks motivate document-level reasoning. Our task stresses cyclic structural evidence retention.`

### Line 365
- Current: `Our method targets the remaining gap: information-preserving SCC handling for cyclic document regions.`
- Issue: Colon-heavy and raw `SCC`.
- Replace with: `Our method targets the remaining gap in information-preserving \scc{} handling for cyclic document regions.`

### Line 368
- Current: `\samcgs{} is complementary: it assumes a record graph and focuses on risk search inside cyclic components.`
- Issue: Colon-heavy.
- Replace with: `\samcgs{} is complementary because it assumes a record graph and focuses on risk search inside cyclic components.`

### Line 373
- Current: `The central idea is to stop treating a long \scc{} as either a flat prompt or an ordinary tree-search path.`
- Issue: `stop treating` is slightly conversational.
- Replace with: `The central idea is to avoid treating a long \scc{} as either a flat prompt or an ordinary tree-search path.`

### Line 378
- Current: `Our benchmark uses injected critical risks so that ground truth is controlled; naturally occurring risks may be messier and require human audit.`
- Issue: Semicolon and `messier` are too informal.
- Replace with: `Our benchmark uses injected critical risks so that ground truth is controlled. Naturally occurring risks may be less controlled and require human audit.`

### Line 378
- Current: `Graph construction quality also matters: missing or spurious edges can change the \scc{}s that the method receives.`
- Issue: Colon-heavy.
- Replace with: `Graph construction quality also matters because missing or spurious edges can change the \scc{}s that the method receives.`

### Line 378
- Current: `Finally, \riskall{} remains difficult in noisy long-contract settings, which is why we report it explicitly rather than replacing it with the easier \riskany{} metric.`
- Issue: Replace repeated `rather than`.
- Replace with: `Finally, \riskall{} remains difficult in noisy long-contract settings, so we report it explicitly instead of replacing it with the easier \riskany{} metric.`

## Appendix

### Lines 387-394
- Current: `Effective compression is computed only on cases whose returned subgraph retains at least one repair-relevant endpoint; it separates useful compression from trivial compression that drops all evidence.`
- Issue: Semicolon can be a period.
- Replace with: `Effective compression is computed only on cases whose returned subgraph retains at least one repair-relevant endpoint. It separates useful compression from trivial compression that drops all evidence.`

### Lines 393-395
- Current: `It is useful for convergence analysis, but it is cumulative by construction and is therefore not a primary success metric.`
- Issue: `but` can be replaced by a more formal connector.
- Replace with: `It is useful for convergence analysis, although it is cumulative by construction and is therefore not a primary success metric.`

### Line 410
- Current: `We construct a representative expert-audit set to verify that the critical structural risks used in our benchmark are recognizable to qualified domain readers, rather than artifacts of hidden system labels.`
- Issue: Replace repeated `rather than`.
- Replace with: `We construct a representative expert-audit set to verify that the critical structural risks used in our benchmark are recognizable to qualified domain readers, not artifacts of hidden system labels.`

### Line 410
- Current: `The audit is \emph{system-blind}: annotators see only paragraph text, paragraph identifiers, and ordinary natural-language instructions.`
- Issue: Colon-heavy.
- Replace with: `The audit is \emph{system-blind}. Annotators see only paragraph text, paragraph identifiers, and ordinary natural-language instructions.`

### Line 427
- Current: `This task is stricter than merely identifying a suspicious sentence: the packet should include enough material for a reviewer to understand and fix the conflict.`
- Issue: Colon-heavy and `merely` is rhetorical.
- Replace with: `This task is stricter than identifying a suspicious sentence because the packet should include enough material for a reviewer to understand and fix the conflict.`

### Line 430
- Current: `Disagreements are preserved for analysis rather than forced into an immediate majority vote.`
- Issue: Replace repeated `rather than`.
- Replace with: `Disagreements are preserved for analysis instead of being forced into an immediate majority vote.`

### Line 433
- Current: `Experts also recognize the injected evidence endpoints: 23 of 24 root/witness endpoint paragraphs receive a majority \emph{clear issue} label, and all 24 receive a majority \emph{clear issue} or \emph{possibly relevant} label.`
- Issue: Colon-heavy.
- Replace with: `Experts also recognize the injected evidence endpoints. In total, 23 of 24 root/witness endpoint paragraphs receive a majority \emph{clear issue} label, and all 24 receive a majority \emph{clear issue} or \emph{possibly relevant} label.`

### Line 462
- Current: `True endpoints are the only role class with near-universal majority recognition: 95.8\% majority clear issue and 100\% majority clear-or-relevant.`
- Issue: Colon-heavy.
- Replace with: `True endpoints are the only role class with near-universal majority recognition, with 95.8\% majority clear issue and 100\% majority clear-or-relevant.`

### Line 462
- Current: `This is expected: the benchmark asks methods to retain the compact repair-relevant endpoints, not to mark every retained context paragraph as intrinsically wrong.`
- Issue: Avoid `This` opening plus colon.
- Replace with: `The pattern is expected because the benchmark asks methods to retain the compact repair-relevant endpoints, not to mark every retained context paragraph as intrinsically wrong.`

### Line 462
- Current: `It also explains why \riskall{} is strict: a method may surface useful context or affected nodes while still missing one side of the contradiction.`
- Issue: Avoid `It` opening plus colon.
- Replace with: `The pattern also explains why \riskall{} is strict, since a method may surface useful context or affected nodes while still missing one side of the contradiction.`

### Line 491
- Current: `The two records describe the same consolidation path but assign incompatible ownership states: fully consolidated with no non-controlling interest versus a retained 20\% non-controlling interest.`
- Issue: Colon-heavy and `but` can be smoother.
- Replace with: `The two records describe the same consolidation path and assign incompatible ownership states, fully consolidated with no non-controlling interest versus a retained 20\% non-controlling interest.`

### Line 498
- Current: `This is the type of structural conflict that a risk-subgraph method should preserve: a reviewer can repair the issue only after seeing both endpoints.`
- Issue: Avoid `This` opening plus colon.
- Replace with: `A risk-subgraph method should preserve this type of structural conflict because a reviewer can repair the issue only after seeing both endpoints.`

### Line 510
- Current: `The original \scc{} is too large to treat as a single atomic finding, yet too cyclic for ordinary path search.`
- Issue: `too cyclic` is informal.
- Replace with: `The original \scc{} is too large to treat as a single atomic finding, yet too recurrence-heavy for ordinary path search.`

### Line 510
- Current: `This is more useful for review than a single node label: a human can inspect the retained endpoints and decide how the conflict should be repaired.`
- Issue: Avoid `This` opening plus colon.
- Replace with: `For review, this is more useful than a single node label because a human can inspect the retained endpoints and decide how the conflict should be repaired.`

### Line 515
- Current: `The implementation uses the same high-level objects as the main paper: a document graph $G$, strongly connected components $S$, local rollout windows $W_t$, relation-first memory $M_t$, online calibrated conflict signals, and a final dynamic core $H_T$.`
- Issue: Colon-heavy.
- Replace with: `The implementation uses the same high-level objects as the main paper, including a document graph $G$, strongly connected components $S$, local rollout windows $W_t$, relation-first memory $M_t$, online calibrated conflict signals, and a final dynamic core $H_T$.`

### Line 602
- Current: `Later rollouts can replace weak records with stronger evidence, but the update is not allowed to drop repeatedly supported critical endpoints merely to obtain a smaller subgraph.`
- Issue: `but` and `merely` make it slightly conversational.
- Replace with: `Later rollouts can replace weak records with stronger evidence, although the update cannot drop repeatedly supported critical endpoints only to obtain a smaller subgraph.`

### Line 607
- Current: `This appendix expands the implementation-level equations that are summarized in Section~3.`
- Issue: Use a LaTeX reference rather than a hard-coded section number.
- Replace with: `This appendix expands the implementation-level equations summarized in Section~\ref{sec:method}.`

### Line 607
- Current: `The main text keeps only the search template, priority score, and core objective; the details below are fixed before evaluation and are not tuned on test cases.`
- Issue: Semicolon can be a period.
- Replace with: `The main text keeps only the search template, priority score, and core objective. The details below are fixed before evaluation and are not tuned on test cases.`

### Line 628
- Current: `For edges we set $w=\beta$ and use edge features such as semantic incompatibility, repeated pair support, reverse-edge evidence, and accumulated conflict.`
- Issue: `accumulated conflict` is incomplete.
- Replace with: `For edges we set $w=\beta$ and use edge features such as semantic incompatibility, repeated pair support, reverse-edge evidence, and accumulated conflict evidence.`

### Line 660
- Current: `They were selected on pilot and smoke runs before the locked evaluation.`
- Issue: `smoke runs` sounds implementation-internal.
- Replace with: `They were selected using pilot checks before the locked evaluation.`

### Line 660
- Current: `Prior MCTS work motivates the structure: UCB/UCT exploration, visit-decayed heuristic priors through progressive bias, AMAF/RAVE-style evidence reuse, and graph/transposition-aware value reuse.`
- Issue: The colon is acceptable but dense; if you want a smoother appendix style, split it.
- Replace with: `Prior MCTS work motivates the structure, including UCB/UCT exploration, visit-decayed heuristic priors through progressive bias, AMAF/RAVE-style evidence reuse, and graph/transposition-aware value reuse.`

### Lines 670-676
- Current: Several table rationales use semicolons, e.g., `LLM names the record as a repair entry; this is closest to the final remediation target.`
- Issue: Table cells can use sentence breaks instead of semicolons.
- Replace with: `LLM names the record as a repair entry. This is closest to the final remediation target.`

### Line 703
- Current: `The following excerpt is the shared evaluator rubric used by both the full-\scc{} \naive{} baseline and the \samcgs{} local-window evaluator:`
- Issue: The colon is acceptable before a quote, but the sentence can be cleaner.
- Replace with: `The following excerpt gives the shared evaluator rubric used by both the full-\scc{} \naive{} baseline and the \samcgs{} local-window evaluator.`

### Line 711
- Current: `The difference is only the input unit.`
- Issue: Too blunt and understates the methodological difference.
- Replace with: `The methods differ in input unit and search procedure.`

### Line 711
- Current: `Thus the comparison is not between two definitions of risk; it is between one-shot full-context evaluation and localized search with evidence compression.`
- Issue: Semicolon can be a period.
- Replace with: `Thus the comparison is not between two definitions of risk. It is between one-shot full-context evaluation and localized search with evidence compression.`

### Line 716
- Current: `without tying the paper to one implementation file.`
- Issue: `tying the paper to` is informal.
- Replace with: `without depending on one implementation file.`

### Line 731
- Current: `the final subgraph is produced by the algorithmic memory and compression steps rather than by a single LLM response.`
- Issue: Replace repeated `rather than`.
- Replace with: `the final subgraph is produced by the algorithmic memory and compression steps instead of a single LLM response.`

### Line 736
- Current: `The selection is intended to cover different forms of authority and structure: technical dependency metadata, public corporate disclosures, official statutory references, and expert-labeled contract clauses.`
- Issue: Colon-heavy.
- Replace with: `The selection covers different forms of authority and structure, including technical dependency metadata, public corporate disclosures, official statutory references, and expert-labeled contract clauses.`

### Line 757
- Current: `Candidate components are filtered by size and record availability, then locked before model evaluation.`
- Issue: Slightly compressed grammar.
- Replace with: `Candidate components are filtered by size and record availability and then locked before model evaluation.`

### Line 760
- Current: `It never adds a new node.`
- Issue: Short `It` sentence after a `The critical benchmark...` sentence is grammatically fine but can be merged.
- Replace with: `No new nodes are added.`

### Line 781
- Current: `A subgraph that includes only the visibly alarming paragraph but omits the distant condition may be too small to support a reliable repair.`
- Issue: `visibly alarming` is slightly informal.
- Replace with: `A subgraph that includes only the obvious-risk paragraph but omits the distant condition may be too small to support a reliable repair.`

### Line 789
- Current: `The same \scc{} block is evaluated by the full-\scc{} direct-subgraph \naive{} baseline and by \samcgs{}; strict rates count unusable structured outputs in the denominator.`
- Issue: Semicolon and possible ambiguity about model/profile matching.
- Replace with: `For each model and profile, the same \scc{} block is evaluated by the full-\scc{} direct-subgraph \naive{} baseline and by \samcgs{}. Strict rates count unusable structured outputs in the denominator.`

### Line 811
- Current: `Reducing the output schema helps full-\scc{} prompting, but does not close the endpoint-retention gap on long CUAD components.`
- Issue: `but` can be replaced with a formal contrast.
- Replace with: `Reducing the output schema helps full-\scc{} prompting, although it does not close the endpoint-retention gap on long CUAD components.`

### Lines 825-828
- Current: Table cells use repeated semicolons, e.g., `One section states when an obligation or remedy applies; a distant referenced section changes the trigger...`
- Issue: In table cells, semicolons are readable but the paper already overuses them.
- Replace with: `One section states when an obligation or remedy applies. A distant referenced section changes the trigger or timing in a way that makes the remedy inconsistent.`

### Line 886
- Current: `Strict rates count unusable structured outputs in the denominator; matched usable-output rates show that the difference is not only output availability.`
- Issue: Semicolon can be a period.
- Replace with: `Strict rates count unusable structured outputs in the denominator. Matched usable-output rates show that the difference is not only output availability.`

## Term And Macro Hygiene

- `LLM`: first textual use should be `large language models (LLMs)`, not `LLM-guided`.
- `MCTS`: first textual use as `Monte Carlo tree search (MCTS)` is fine.
- `SCC`: first textual use as `strongly connected components (SCCs)` is fine, but later text should consistently use `\scc{}` or raw `SCC`, not both.
- `SEC EX-21`: first textual use should expand `SEC` as `U.S. Securities and Exchange Commission Exhibit 21 (SEC EX-21)`.
- `BGB`: first textual use should be `German Civil Code (BGB)` if `BGB` appears in text, tables, or captions before an expansion.
- `CUAD`: first textual use should be `Contract Understanding Atticus Dataset (CUAD)`.
- `OC`: first textual use should be `online calibrated conflict signal (\oc{})`.
- `UCB`, `UCT`, `AMAF`, and `RAVE`: these are standard in MCTS papers, but ACL readers are broader. Consider one compact expansion in the appendix or a footnote if space allows.

## Highest-Impact Edits

If space or time is limited, I would prioritize these first:

1. Fix the abstract first-use abbreviations and replace the abstract `but`.
2. Fix the ungrammatical sentence at line 81.
3. Remove defensive wording such as `cherry-picking`, `not merely`, and `messier`.
4. Reduce colon/semicolon density in the introduction, method explanation, and appendix audit.
5. Replace repeated `rather than` with `instead of`, `not`, or a direct contrast where the meaning stays unchanged.
