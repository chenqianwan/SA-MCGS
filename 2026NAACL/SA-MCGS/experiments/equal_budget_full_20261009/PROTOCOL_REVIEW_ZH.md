# 三小模型全量同预算实验：输入与科学协议审阅

范围为 Llama-3.1-8B-Instruct、Kimi-VL-A3B-Instruct、Qwen3.5-9B；每模型沿用同一80个注入变体，来自20个物理SCC。本审阅只负责输入、科学配置与离线预检，不代表新runner、客户端、tokenizer或集群部署已验收。

## 已确认的输入来源与最简接口

采用 `kimi_qwen35_three_methods_20260924/runner/repo` 的冻结可移植bundle。Kimi、Qwen3.5与Llama历史下载计划逐 `case_uid` 对照：有序节点、完整稳定身份、注入身份、来源文件/SA记录哈希、main顺序、SCC fingerprint均一致。80例的领域分布为CUAD 40、SEC EX-21 20、BGB 12、Debian 8；每个物理SCC有4种注入，不能把80变体当作80个独立来源。

建议直接复用旧 `runner/base_launcher.py` 的只读加载接口，不调用其 `prepare`，因为后者会写旧实验协议并固定旧模型及内部并发8：

```python
# L由importlib从旧runner/base_launcher.py加载；不运行其CLI。
manifest = L.verify_bundle()
cost = L.import_science()
graphs = L.restore_graphs(cost, manifest)
plan = json.loads((L.ROOT / "portable_data/qwen80_case_plan.json").read_text())
for case in plan:
    case["source_result_file"] = str(L.ROOT / case["source_result_repo_relpath"])
cost.validate_case_plan(plan, graphs)
graph, scc, root, labels = cost.prepare_injected_case(case, graphs)
```

图由bundle内冻结的gzip恢复并验证内容revision，不重新运行Stage1。`case_id/model`可为新模型换名，`case_uid`、ordered IDs、注入身份与来源哈希保持原值。不能按旧成绩选择案例、替换源SCC或调整注入。

`preflight/audit_inputs.py`禁用网络与dotenv读取，不创建LLM客户端；会检查bundle哈希、重建80个注入输入、输出安全可见字段及每例哈希。结果见 `preflight/input_audit.json`、`case_input_manifest.json`、`visible_inputs/`。实际送入新模型的表示应再次记录哈希并与这个输入身份对应；本预检不等于已经验证新runner的实际请求。

## SA配置与可部署输出

历史三模型的完整SA配置完全一致：60 rollout、window 4、temperature 0.4、输出上限2048、内部并发8，`current`压缩配置及relation-first/critical-pair机制。新方案仅把内部并发改为1，其余配置的目标值保存在 `preflight/proposed_sa_config.json`。

内部并发8→1会改变自适应搜索完成顺序与后续轨迹，是必须披露的协议变化。需要本次同期重跑SA来确定预算B，不能把历史SA输出直接拼成新同预算主结果。病例并发/多GPU任务分配属于另一个层次，可用于吞吐，但必须保证每个病例有独立随机状态和缓存；不能让并发病例共同重设全局RNG，导致轨迹受调度影响。记录Python random/哈希种子、真实采样参数与模型tokenizer版本。

主输出使用原生H：SA的 `evidence_risk_subgraph_nodes`，LEA的 `lea_risk_subgraph_nodes`，Full-SCC的 `direct_risk_subgraph_nodes`。已逐例核对238个历史有效SA结果，`core_evidence_risk_subgraph_nodes`与可部署的`evidence_risk_subgraph_nodes`完全相等。旧 `risk_subgraph_nodes` 含GT锚定后处理，不得用于推理、judge或主指标。

GT仅用于确定固定注入、验证身份、离线评分。judge输入使用白名单：可见条款/边、匿名候选排名、候选H、模型声明的冲突。不要把完整result、case plan或metadata序列化给judge；这些对象含root/risk/evidence标签、命中指标及GT后处理字段。选中一个完整候选，不做GT best-of-N、不按真实Risk-all取最大。

## 同预算必须预先固定的边界

每模型、每例先运行本次SA；以真实usage的输入+输出总tokens定义B，包括解析重试和失败请求已经返回的usage。两个baseline各自的全部候选、重试及judge总消耗均不超过该B。缓存重放不应被重复计费，也不允许删除缓存重新抽样。SA响应与采证轨迹不能提供给baseline。

动态judge预留应基于模型实际tokenizer、真实chat template和当前已生成候选；未知的下一候选仍需有明确长度上界，不能将尚未生成的judge文本称作精确已知。候选输出reason截断、排序与匿名映射规则先冻结，并计入真实候选集judge调用成本。预算不足时保留原候选并停止，不拿剩余额度造无意义调用；每例报告实际tokens/B、候选数、judge开销与停止原因。因此即使上限匹配，仍不保证实际tokens完全相等。

需要新主协议明确而不能运行时临时决定的情况：

- SA出现科学schema失败、未完成60轮：保留该失败，不按结果重跑。建议仍以已产生的实际usage作为B并标记`sa_terminal_failed`；不能默默删掉该病例。基础设施故障单独记录，不能伪装成模型失败或用另一条成功轨迹替换预算。
- 若B不足以生成一个完整baseline候选，保留未生成/预算停止状态，计入计划分母，不缩短原文或换简单案例。
- 一候选时可以直接输出，不调用judge；judge失败时不能根据GT或效果回退挑选。候选次数是否另有限制必须预先固定，并报告由此造成的剩余额度。
- 未知usage的请求在对账完成前不能被当作零成本；严格预算需有保守占用或暂停规则。

## Parser、温度与运行变化

历史三小模型：JSON最多3次尝试，耗尽按旧流程返回`{}`，SDK retries=0；局部窗口回退不自动使整例失败。旧Kimi SA有40例/457个耗尽窗口，Qwen3.5有21例/48个，Llama有24例/49个；这是实际算法执行路径，不能只看整例strict=0就说没有解析问题。

四例GPT pilot使用了不同策略（两次解析与严格guard）。新全量实验若希望沿用原方法，不能无说明复制这一策略。应在新主协议中选定一套所有方法统一的解析规则，记录请求尝试、修复成功、窗口回退、整例失败和基础设施故障；不能在看结果后放宽parser再选分数较高版本。任何改进parser应对全部模型/方法一致应用，并与历史严格结果分开标注。

历史One-shot温度0、输出12000；GPT pilot Full重复候选温度0.4。新Full重复采样的温度同样需明确冻结。SA/LEA局部温度0.4、输出2048。Qwen3.5必须显式`enable_thinking=false`，不继承旧科学代码按模型名包含`qwen`触发的8192托管端点限制；实际max output、client请求与服务tokenizer均需一致。

## 历史计算量依据

以下均来自80个历史SA结果的 `llm_usage_summary`，包括失败使用量，不是本次运行预算承诺：

| 模型 | SA总tokens | 每例均值 | P95 | 最大值 |
|---|---:|---:|---:|---:|
| Llama 3.1 8B | 17,038,490 | 212,981 | 347,538 | 369,080 |
| Kimi-VL-A3B | 21,330,929 | 266,637 | 497,834 | 569,239 |
| Qwen3.5-9B | 13,230,614 | 165,383 | 303,145 | 431,579 |

三模型历史SA合计51,600,033 tokens。如果本次每例B恰等于历史消耗，SA与两个baseline各用至B时总量上界为154,800,099 tokens。新并发/parser会改变B，因此这是规模参考。历史请求runtime相加包含并发重叠，不能除以GPU数直接当作工期。完整三方法历史usage保存在 `preflight/historical_workload.json`。

最终指标仍以每模型80计划变体为分母，失败/缺失分类分开；H/压缩率保留有效分母。除Root@3与风险端点Risk-all，还应保留Root@1/MRR、端点召回及含bridge的Evidence-all/recall。它们只评价注入gold，不能把H中其他节点直接算为误报，也不能宣称自然风险证据完整。
