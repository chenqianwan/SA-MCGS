# E0. Matched / Valid-only / Error Handling

目的：把 strict rate、valid-only rate、matched no-error rate 分开，回答 reviewer 关于解析失败是否被 cherry-pick 的问题。

- Strict 分母：Naive=320, SA-MCGS=320。
- Matched no-error 分母：261 个同一 SCC + 同一模型 + 同一注入的可比 pair。

| Scope | Method | N | Errors | Root@3 | Risk-any | Risk-all | Compression | Effective Compression |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| strict_all_records | naive | 320 | 59 | 48% | 72% | 47% | 67% | 66% |
| strict_all_records | sa-mcgs | 320 | 0 | 81% | 98% | 78% | 53% | 53% |
| valid_only | naive | 261 | 0 | 59% | 88% | 57% | 67% | 66% |
| valid_only | sa-mcgs | 320 | 0 | 81% | 98% | 78% | 53% | 53% |
| matched_no_error_pairs | naive | 261 | 0 | 59% | 88% | 57% | 67% | 66% |
| matched_no_error_pairs | sa-mcgs | 261 | 0 | 83% | 98% | 77% | 52% | 52% |

论文写法建议：主表用 strict；补充表同时给 valid-only 和 matched no-error。这样 Naive 的 59 个解析失败不会被忽略，也不会把 SA-MCGS 的优势只解释成 JSON 稳定性。
