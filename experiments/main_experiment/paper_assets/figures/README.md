# Paper Figure README

这个目录是论文写作唯一推荐引用的图表入口。主文图表从这里拿，避免误用旧的 diagnostic / smoke / balanced exploratory 图。

| ID | File | Section | Explanation | Main Text? |
|---|---|---|---|---|
| Figure 1 | `fig01_sa_mcgs_framework_architecture.svg/png` | Method | Frontend architecture diagram from demo.html: validated cyclic domains, Tarjan SCC split, three SA-MCGS contributions, and pluggable pruning adapters. | Yes |
| Figure 2 | `fig02_main_metrics_strict.pdf/png` | Main Results | Composite main result: strict Root@3/Risk-any/Risk-all, reliability/error burden, model-level Risk-all, and domain-level difficulty. | Yes |
| Figure 3 | `fig03_main_by_scc_size.pdf/png` | Main Results / Analysis | Composite SCC-size analysis: Risk-all by exact size, SA-minus-Naive gains, compression by size, and bucketed paper view. | Yes |
| Figure 4 | `fig04_budget_prefix_convergence.pdf/png` | Analysis | Rollout convergence: root retention, Risk-any, Risk-all, effective OC, coverage, compression, and per-model Risk-all curves. | Yes |
| Figure 5 | `fig05_compression_profile_tradeoff.pdf/png` | Analysis / Appendix | Pareto trade-off between risk retention and compression profile; explains why current/default sacrifices some compression for endpoint retention. | Maybe |
| Figure 6 | `fig06_representative_scc_collapse.pdf/png` | Case Study | Representative long-SCC case narrative: original cycle context, final dynamic core, rollout trace, and same-case Naive-vs-SA outcome. | Maybe |
| Figure A2 | `figA2_naive_output_burden.pdf/png` | Appendix | Naive output-burden fairness control: full direct-subgraph output versus lite output on long CUAD cases. | No |

口径规则：

- 主实验图只使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。
- `balanced`、`conservative`、Gemini Flash、Wikipedia exploratory、旧 memory_stress diagnostic 不进入主图。
- `Effective OC` 只作为 rollout 发现过程的辅助曲线，不作为主命中指标。
