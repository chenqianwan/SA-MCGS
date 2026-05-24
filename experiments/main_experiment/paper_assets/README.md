# Main Experiment Paper Assets

这是最终论文写作使用的稳定图表与标注资产目录。后续写 paper 时优先从这里引用，不再直接从 `cross_domain/results/` 或临时 dashboard 拿图。

## Directory

- `figures/`：论文主文和 appendix 图，含 `README.md` 解释每张图。
- `tables/`：论文表格 CSV/Markdown 源文件。
- `human_annotation_pack/`：专家标注小包，含精选 case、可填写 HTML、本地 Excel 导出依赖和 zip。

## Locked Main Experiment Scope

- Profile: `current/default`
- Injection: `memory_stress` internally `structural_simple_v2`
- Severity: `critical`
- Models: `gpt-4o`, `deepseek-v3`, `qwen2.5-72b`, `gemini-2.5-pro`
- Domains: Debian, SEC EX-21, BGB, CUAD
- Budget: SA-MCGS `60` rollouts
- Size: `80` SCC blocks per model, `320` model-case pairs, `640` method-level records

## Recommended Main-paper Assets

- Figure 1: `figures/fig01_sa_mcgs_framework_architecture.svg` / `.png`
- Figure 2: `figures/fig02_vanilla_mcts_scc_failure.png`
- Table 1: `tables/tab01_mcts_scc_motivation.md` / `.csv`
- Table 2: `tables/tab02_domain_coverage_authority.md` / `.csv`
- Table 3: `tables/tab03_reliability_strict.md` / `.csv`
- Main-result metric source: `tables/tab03_main_results_strict.md` / `.csv`
- Figure 3: `figures/fig02_main_results_composite.pdf`
- Figure 4: `figures/fig04_budget_prefix_convergence.pdf`
- Figure 5: `figures/fig05_compression_profile_tradeoff.pdf`
- Appendix figure: `figures/fig03_main_by_scc_size.pdf`
- Appendix figure: `figures/fig06_representative_scc_collapse.pdf`

## Human Annotation

- Zip: `human_annotation_pack/human_annotation_pack.zip`
- Browser entry: `human_annotation_pack/annotation_interface.html`
- Selected-case CSV: `human_annotation_pack/human_annotation_cases.csv`
- Internal full candidate manifest: `human_annotation_pack/full_candidate_manifest_not_for_experts.csv`
