# HTTP 503 恢复范围核验

本步骤只读取已有结果并冻结恢复范围，不发起 API 请求。

- 原始无效基线：170 项；历史有效基线 150 项保持不变；历史 SA 参考 160 项保持不变。
- 42 项只重试选择器，复用原有 201 个完整候选，不补跑或新建候选。
- 119 项恢复候选阶段；严格选取 scientific_failure 且错误明确为 HTTP 503 的 1,284 个候选。
- 其余 9 项按原结果保留，不恢复。其中包含试跑阶段的 GPT-4o Full-SCC 第 11、12 项。
- 每个恢复候选的调用范围由 usage_before/usage_after.accounted_tokens 与原始账本累计计费对齐；末次调用必须与错误中的 request key 一致并明确返回 503。
- 已成功的调用从原始缓存复用；解析失败、HTTP 400、连接错误等不作为新增重试依据。
- 每个已确认的 503 请求最多新增两次传输重试。此准备步骤不清空历史用量或 503 预留额度。
- 所有读取的原始最终结果、候选、调用缓存、账本和合并结果均记录 SHA-256。试跑路径来自其 reporting_source，绝不按试跑序号映射到新增 70 项目录。

## 按模型和方法汇总

| 模型 | 方法 | 候选恢复 | 仅选择器 | 不恢复 |
|---|---|---:|---:|---:|
| gpt-4o | lea | 22 | 8 | 0 |
| gpt-4o | full-scc | 31 | 14 | 7 |
| gemini-2.5-pro | lea | 46 | 3 | 0 |
| gemini-2.5-pro | full-scc | 20 | 17 | 2 |

## 保留原结果的 9 项

| 来源 | 模型 | 方法 | 原目录序号 | 主实验顺序 |
|---|---|---|---:|---:|
| remaining70 | gemini-2.5-pro | full-scc | 25 | 25 |
| remaining70 | gemini-2.5-pro | full-scc | 31 | 31 |
| remaining70 | gpt-4o | full-scc | 1 | 1 |
| remaining70 | gpt-4o | full-scc | 2 | 2 |
| remaining70 | gpt-4o | full-scc | 4 | 4 |
| remaining70 | gpt-4o | full-scc | 5 | 5 |
| remaining70 | gpt-4o | full-scc | 7 | 7 |
| retained_pilot10 | gpt-4o | full-scc | 12 | 21 |
| retained_pilot10 | gpt-4o | full-scc | 11 | 26 |

已冻结 5486 个源文件的校验值。
