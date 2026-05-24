# E0. Matched / Valid-only / Output Availability

目的：把 strict rate、valid-only rate、matched usable-output rate 分开，回答 reviewer 关于不可用结构化输出是否被 cherry-pick 的问题。

- Strict 分母：Naive=320, SA-MCGS=320。
- Matched usable-output 分母：261 个同一 SCC + 同一模型 + 同一注入的可比 pair。

| Scope | Method | N | Unavailable outputs | Root@3 | Risk-any | Risk-all | Compression | Effective Compression |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| strict_all_records | naive | 320 | 59 | 48% | 72% | 47% | 67% | 66% |
| strict_all_records | sa-mcgs | 320 | 0 | 81% | 98% | 78% | 53% | 53% |
| valid_only | naive | 261 | 0 | 59% | 88% | 57% | 67% | 66% |
| valid_only | sa-mcgs | 320 | 0 | 81% | 98% | 78% | 53% | 53% |
| matched_usable_output_pairs | naive | 261 | 0 | 59% | 88% | 57% | 67% | 66% |
| matched_usable_output_pairs | sa-mcgs | 261 | 0 | 83% | 98% | 77% | 52% | 52% |

论文写法建议：主表用 strict；补充表同时给 valid-only 和 matched usable-output。这样 Naive 的 59 个不可用结构化输出不会被忽略，也不会把 SA-MCGS 的优势只解释成输出格式稳定性。
