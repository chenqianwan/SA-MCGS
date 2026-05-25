# Paper Figure README

这个目录是论文写作唯一推荐引用的图表入口。主文图表从这里拿，避免误用旧的 diagnostic / smoke / balanced exploratory 图。

| ID | File | Section | Explanation | Main Text? |
|---|---|---|---|---|
| Figure 1 | `fig01_sa_mcgs_framework_architecture.svg/png` | Method | Frontend architecture diagram from demo.html: validated cyclic domains, Tarjan SCC split, three SA-MCGS contributions, and pluggable pruning adapters. | Yes |
| Figure 2 | `fig02_vanilla_mcts_scc_failure.png` | Method | Visual motivation for why vanilla TreeMCTS fails on SCCs: path-copy expansion, budget dilution, Q-value flattening, and the SA-MCGS collapse alternative. | Yes |
| Figure 3 | `fig02_main_results_composite.pdf/png` | Main Results | Composite main-result figure: oracle-risk Naive versus SA-MCGS, plus SCC-size breakdown of endpoint retention and compression. | Yes |
| Figure A1 | `fig03_main_by_scc_size.pdf/png` | Appendix | Standalone SCC-size analysis retained as a backup asset; the main text uses the composite Figure 3. | No |
| Figure 4 | `fig04_budget_prefix_convergence.pdf/png` | Analysis | Rollout convergence: strict success curves, evidence coverage versus compression, and citable budget checkpoints. | Yes |
| Figure 5 | `fig05_compression_profile_tradeoff.pdf/png` | Analysis / Appendix | Pareto trade-off between risk retention and compression profile; explains why current/default sacrifices some compression for endpoint retention. | Maybe |
| Figure A2 | `fig06_representative_scc_collapse.pdf/png` | Case Study | Representative long-SCC case narrative: original cycle context, final dynamic core, rollout trace, and same-case Naive-vs-SA outcome. | Maybe |
| Figure A2 | `figA2_naive_output_burden.pdf/png` | Appendix | Naive output-burden fairness control: full direct-subgraph output versus lite output on long CUAD cases. | No |

口径规则：

- 主实验图使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。
- Figure 3 的 Naive baseline 是 `oracle_risk_top3` over ten full-SCC Naive attempts，图例写作 `oracle-risk Naive`。
- `balanced`、`conservative`、Gemini Flash、Wikipedia exploratory、旧 memory_stress diagnostic 不进入主图。
- `Effective OC` 只作为 rollout 发现过程的辅助曲线，不作为主命中指标。
