# Main Experiment Lock

This directory defines the **paper main experiment** for ARR/EMNLP writing.

It does not move or duplicate raw result files. Instead, it locks the exact result scope that the paper, dashboard, tables, and case studies should use.

## Canonical Scope

Use this as the only main-result setting:

```text
profile: current/default
inject profile version: structural_simple_v2
severity: critical
models: gpt-4o, deepseek-v3, qwen2.5-72b, gemini-2.5-pro
domains: Debian, SEC EX-21, BGB, CUAD
cases: 80 SCC blocks per model
methods: Naive direct-subgraph, SA-MCGS
budget: 60 rollouts for SA-MCGS
```

This corresponds to:

- `320` model-case pairs.
- `640` method-level records, because each model-case pair has Naive and SA-MCGS.

## Canonical Status Files

The main experiment is assembled only from these status files under `experiments/cross_domain/results/`:

1. `critical_paper_v3_b60_severity_grid_status.json`
   - `gpt-4o` and `deepseek-v3`
   - current/default profile

2. `critical_qwen_current_full80_b60_severity_grid_status.json`
   - `qwen2.5-72b`
   - current/default profile

3. `gemini25pro_health_current_balanced_b60_severity_grid_status.json`
   - small Gemini Pro health/checkpoint run
   - used only where it contributes canonical current/default rows after deduplication

4. `critical_gemini25pro_current_balanced_partA_b60_severity_grid_status.json`
   - `gemini-2.5-pro`
   - current/default and balanced records; main experiment uses only current/default

5. `critical_gemini25pro_current_balanced_partB_b60_severity_grid_status.json`
   - `gemini-2.5-pro`
   - current/default and balanced records; main experiment uses only current/default

The dashboard deduplicates records by:

```text
domain, scc_id, scc_size, model, method, template, severity, profile
```

## Main Dashboard

Use:

```bash
python experiments/cross_domain/final_results_dashboard.py --port 8777
```

The dashboard reads the files above and reports:

- strict rate
- valid-only context where needed
- error count
- Root@3
- Risk-any
- Risk-all
- compression
- convergence curves
- SCC-size breakdown

## Paper Supplements

The paper-facing supplement artifacts are in `supplements/`:

- `E0_MATCHED_VALID_ONLY.md`: strict vs valid-only vs matched-no-error rates.
- `E1_NAIVE_OUTPUT_BURDEN_CONTROL.md`: CUAD long-SCC Naive-lite output-burden control.
- `E2_BUDGET_PREFIX_CONVERGENCE.md`: SA-MCGS rollout-prefix convergence.
- `E3_COMPRESSION_PROFILE_ABLATION.md`: current/default vs balanced compression profile.
- `E5_PROMPT_RUBRIC_PARITY.md`: shared risk-rubric and prompt fairness note.

These supplements are complete except for E4, the human audit owned outside this directory. The LaTeX paper should be rewritten only after these files are treated as the evidence source.

## What Is Not Main Result

Do not mix these into the main tables:

- `balanced`
- `conservative`
- `aggressive`
- old `memory_stress` diagnostic runs
- Gemini 2.5 Flash
- Wikipedia-only exploratory runs
- 10-case compression sweep
- smoke runs
- partial historical debugging runs

These can be mentioned only in appendix, ablation, or experiment-evolution notes.

## Main Result Numbers

Current strict main results:

| Metric | Naive | SA-MCGS |
|---|---:|---:|
| Root@3 | 48% | 81% |
| Risk-any | 72% | 98% |
| Risk-all | 47% | 78% |
| Compression | 67% | 53% |
| Method errors | 59/320 | 0/320 |

SCC-size buckets:

| SCC bucket | Root@3 | Risk-any | Risk-all |
|---|---:|---:|---:|
| short <=12 | 54% -> 89% | 88% -> 99% | 55% -> 83% |
| mid 14-20 | 43% -> 77% | 59% -> 99% | 40% -> 80% |
| long >=24 | 45% -> 71% | 56% -> 92% | 41% -> 65% |

## Writing Rule

When writing the paper:

1. Main tables and claims must use this directory's scope.
2. Any result outside this scope must be explicitly labeled as appendix, ablation, diagnostic, or exploratory.
3. Do not switch compression profile to make a figure look better.
4. Do not report cumulative Effective OC as a standalone main metric; use it only as discovery/convergence support.

## Paper Asset Directory

论文图表和人工标注材料统一放在 [`paper_assets/`](paper_assets/)，后续写 paper 时优先引用这里的稳定文件：

- [`paper_assets/figures/`](paper_assets/figures/)：主文和 appendix 图，目录内 `README.md` 解释每张图。
- [`paper_assets/tables/`](paper_assets/tables/)：主表和补充表的 CSV/Markdown 源。
- [`paper_assets/human_annotation_pack/human_annotation_pack.zip`](paper_assets/human_annotation_pack/human_annotation_pack.zip)：给专家标注的精选小包，含 12 个 case、可填写中英文 HTML、节点文本弹窗和一键 Excel 导出。

口径提醒：主实验图表只使用 `current/default + critical + structural_simple_v2 + 4 models + 80 SCC blocks/model`。旧 diagnostic、smoke、balanced exploratory 不作为主结果。

