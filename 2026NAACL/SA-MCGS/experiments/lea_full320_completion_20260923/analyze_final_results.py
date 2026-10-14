"""Generate a descriptive final analysis from the verified, complete paired set.

No API requests; raw outputs and frozen experiment inputs remain unchanged.
"""
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = ["gpt-4o", "gemini-2.5-pro", "qwen2.5-72b", "deepseek-v3"]
LABELS = dict(zip(MODELS, ["GPT-4o", "Gemini 2.5 Pro", "Qwen2.5-72B", "DeepSeek-V3"]))
METHODS = {"one-shot": "One-shot", "lea": "LEA", "sa-mcgs": "Full-SCC"}
METRICS = ["root_at_3", "risk_any", "risk_all"]


def read(name):
    return json.loads((HERE / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(rows):
    comp = [float(r["compression"]) for r in rows if r["compression"] != ""]
    result = {"n": len(rows), "strict_invalid_n": sum(r["strict_invalid"] == "True" for r in rows),
              "physical_scc_n": len({r["physical_scc_uid"] for r in rows}),
              "compression": sum(comp) / len(comp) if comp else None,
              "compression_valid_n": len(comp)}
    for metric in METRICS:
        result[metric + "_success_n"] = sum(int(r[metric]) for r in rows)
        result[metric] = result[metric + "_success_n"] / len(rows)
    return result


def paired(rows):
    cases = defaultdict(dict)
    for row in rows:
        cases[row["stable_case_uid"]][row["method"]] = row
    result = {"n": len(cases)}
    for metric in METRICS:
        counts = {"full_only": 0, "lea_only": 0, "both": 0, "neither": 0}
        clusters = defaultdict(int)
        for case in cases.values():
            full, lea = case["sa-mcgs"], case["lea"]
            f, l = int(full[metric]), int(lea[metric])
            counts["both" if f and l else "full_only" if f else "lea_only" if l else "neither"] += 1
            clusters[full["physical_scc_uid"]] += f - l
        counts["delta_pp"] = 100 * (counts["full_only"] - counts["lea_only"]) / len(cases)
        counts["physical_scc_direction"] = {
            "full_better": sum(v > 0 for v in clusters.values()),
            "lea_better": sum(v < 0 for v in clusters.values()),
            "tie": sum(v == 0 for v in clusters.values())}
        result[metric] = counts
    return result


def main():
    verification = read("verification.json")
    assert verification["verification_passed"] and verification["completion_status"] == "complete"
    assert verification["available_lea_cells"] == 320 and verification["matched_method_records"] == 960
    path = HERE / "matched_3method_case_metrics.csv"
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len({(r["model"], r["stable_case_uid"], r["method"]) for r in rows}) == 960
    assert {r["model"] for r in rows} == set(MODELS)
    assert {r["method"] for r in rows} == set(METHODS)
    assert all(r["available"] == "True" and r["identity_exact"] == "True" for r in rows)
    assert all(sum(r["model"] == model and r["method"] == method for r in rows) == 80
               for model in MODELS for method in METHODS)
    groups, pairs = {}, {}
    for model in MODELS:
        model_rows = [r for r in rows if r["model"] == model]
        groups[model] = {method: aggregate([r for r in model_rows if r["method"] == method]) for method in METHODS}
        pairs[model] = {"overall": paired(model_rows), "domain": {}, "scale": {}}
        for dimension in ("domain", "scale"):
            for name in sorted({r[dimension] for r in model_rows}):
                selected = [r for r in model_rows if r[dimension] == name]
                pairs[model][dimension][name] = {
                    "paired": paired(selected),
                    "methods": {m: aggregate([r for r in selected if r["method"] == m]) for m in METHODS}}
    overall = {m: aggregate([r for r in rows if r["method"] == m]) for m in METHODS}
    quality = read("ANALYSIS_QWEN_AUDIT_NOTES.json")["output_quality"]
    qwen_rows = [r for r in rows if r["model"] == "qwen2.5-72b"]
    exhausted = {}
    for row in qwen_rows:
        if row["method"] == "lea":
            source = Path(row["source_file"])
            assert "sha256:" + sha(source) == row["source_sha256"]
            exhausted[row["stable_case_uid"]] = json.loads(source.read_text())["json_parse_exhausted_windows"]
    assert sum(v > 0 for v in exhausted.values()) == quality["qwen_parse_exhaustion_affected_cases"] == 34
    assert sum(exhausted.values()) == quality["qwen_parse_exhaustion_windows"] == 101
    diagnostics = {}
    for name, predicate in {
        "non_cuad": lambda r: r["domain"] != "cuad",
        "cuad_no_exhaustion": lambda r: r["domain"] == "cuad" and exhausted[r["stable_case_uid"]] == 0,
        "cuad_exhaustion": lambda r: r["domain"] == "cuad" and exhausted[r["stable_case_uid"]] > 0,
    }.items():
        selected = [r for r in qwen_rows if predicate(r)]
        diagnostics[name] = {m: aggregate([r for r in selected if r["method"] == m]) for m in METHODS}
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "api_calls": 0,
        "input_sha256": {n: sha(HERE / n) for n in ["verification.json", "matched_3method_case_metrics.csv",
            "frozen_manifest.json", "frozen_pricing.json", "frozen_runner_protocol.json", "ANALYSIS_QWEN_AUDIT_NOTES.json"]},
        "groups": groups, "overall_descriptive": overall, "paired_full_vs_lea": pairs,
        "output_quality": quality, "qwen_posthoc_diagnostics": diagnostics,
        "completion_budget": verification["budget_ledger_snapshot"],
        "statistical_scope": "20 physical SCCs x 4 variants, shared across four models. Descriptive counts only; no independence assumption or p-values."
    }
    (HERE / "RESULTS_ANALYSIS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 四模型 LEA 补齐后的结果分析", "",
        "**Full-SCC 的完整风险证据保留收益依赖模型：GPT 和 Qwen 的提升明显，Gemini 与 DeepSeek 总体持平。当前结果不支持所有模型、所有指标全面领先的表述。**", "",
        "LEA 已完成 320/320：历史复用147例，新增173例。三方法在相同案例上共960条记录，身份、配置和指标重算核验通过；本次分析没有新增模型调用。", "",
        "## 完整主表", "",
        "每行80例。Root@3 是注入根节点进入最终排序前三；Risk-any / Risk-all 是保留子图包含至少一个 / 全部预先冻结的风险端点，并非发现所有现实法律风险。Compression 是删除节点比例，越高表示子图越小。", "",
        "| 模型 | 方法 | Root@3 | Risk-any | Risk-all | Compression | 严格无效 |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for model in MODELS:
        for method, label in METHODS.items():
            g = groups[model][method]
            values = [f"{100*g[k]:.2f}%" for k in METRICS + ["compression"]]
            lines.append(f"| {LABELS[model]} | {label} | " + " | ".join(values) + f" | {g['strict_invalid_n']} |")
    lines += ["", "Full-SCC 使用最终 `core_evidence_risk_subgraph_nodes`，不使用带额外真值扩展的输出。严格无效结果在检测指标中计0；Compression 只对有效输出平均，因此 One-shot 的有效输出压缩率需要结合失败数量阅读。", "",
        "## Full-SCC 相对 LEA 的配对变化", "",
        "下表的独占成功指同一案例中只有该方法达到 Risk-all；净提升不是两个不相交样本的比较。", "",
        "| 模型 | Root@3 净变化 | Risk-all 净变化 | Risk-all Full独占 / LEA独占 | 物理SCC方向：Full优 / LEA优 / 持平 |",
        "|---|---:|---:|---:|---:|"]
    for model in MODELS:
        p = pairs[model]["overall"]
        a, c = p["risk_all"], p["risk_all"]["physical_scc_direction"]
        lines.append(f"| {LABELS[model]} | {p['root_at_3']['delta_pp']:+.2f} pp | {a['delta_pp']:+.2f} pp | {a['full_only']} / {a['lea_only']} | {c['full_better']} / {c['lea_better']} / {c['tie']} |")
    full, lea = overall["sa-mcgs"], overall["lea"]
    lines += ["", f"四模型合计320个模型×案例对：Risk-all 为 Full-SCC {full['risk_all_success_n']}/320（{100*full['risk_all']:.2f}%）对 LEA {lea['risk_all_success_n']}/320（{100*lea['risk_all']:.2f}%），净增 {100*(full['risk_all']-lea['risk_all']):.2f} 个百分点；Root@3 为 {full['root_at_3_success_n']}/320 对 {lea['root_at_3_success_n']}/320。但 Risk-any 为 {full['risk_any_success_n']}/320 对 {lea['risk_any_success_n']}/320，Full-SCC 略低。这只是描述性汇总，不代表320个独立样本。", "",
        "- GPT：Risk-all 在四个领域、三个规模组均领先，且逐例保留节点数量与 LEA 相同。这是最一致的证据。",
        "- Gemini：Root@3 与 Risk-all 总体持平，Full-SCC 压缩率增加4.60个百分点；large组压缩率68.20%对52.94%，但 Root@3 为16/20对19/20，存在取舍。One-shot 的 Root@3 90%、Risk-all 85%还略高于两种图方法，不能把 Gemini 写成模型能力差。",
        "- DeepSeek：Risk-all 持平，Root@3 只多1例。BGB的 Root@3 为 Full 11/12对LEA 5/12，CUAD则为25/40对31/40；large组LEA的 Root@3 和 Risk-all 均多3例。总体均值隐藏了领域和规模的方向反转。",
        "- Qwen：Risk-all 净多25例；BGB、CUAD、SEC领先，Debian为5/8对7/8。需要结合下面的输出质量诊断解释。", "",
        "## Qwen 输出质量限制", "",
        "80例中34例（42.5%）存在 JSON 三次解析失败后的默认回退，共101个窗口；全部位于CUAD，即该领域34/40例受到影响。最终严格无效数为0，只说明最终结果满足有效性规则，不说明每个窗口都成功解析。", "",
        "1268次非缓存逻辑评估产生1695次实际API调用，额外427次重试；529次调用以 `length` 结束且输出达到2048 token上限。达到上限不等于最终解析失败，但说明输出长度和格式可靠性是需要排查的因素。", "",
        "这些案例按原冻结协议保留在主结果中。当前结果测量的是固定2048输出预算、重试与回退规则下的完整方法表现，不能把全部差距直接归因于搜索策略。也不能反过来把全部差距归因于格式失败：", "",
        "| 事后诊断子集 | N | Full-SCC Risk-all | LEA Risk-all |",
        "|---|---:|---:|---:|"]
    for name, label in [("non_cuad", "非CUAD，无LEA解析耗尽"), ("cuad_no_exhaustion", "CUAD，无LEA解析耗尽"), ("cuad_exhaustion", "CUAD，有LEA解析耗尽")]:
        d = diagnostics[name]
        n = d["lea"]["n"]
        lines.append(f"| {label} | {n} | {d['sa-mcgs']['risk_all_success_n']}/{n} | {d['lea']['risk_all_success_n']}/{n} |")
    lines += ["", "这些子集仅用于诊断，不能通过剔除困难案例改写主表，也不能构成因果归因。新补跑GPT6例、Gemini7例、DeepSeek80例的解析耗尽均为0；历史GPT74例和Gemini73例缺少该字段，诊断状态未知。", "",
        "## 对后续工作的判断", "",
        "四模型覆盖已补齐，无须为补齐主表继续大规模重跑。现有数据足够补做 LEA 与 Full-SCC 的按领域、按规模配对比较，原来只画 Full-SCC 的性能分析可以用这些现成结果扩展。", "",
        "优先值得追加的是 Qwen 的小规模输出长度敏感性诊断：预先固定涵盖受影响与未受影响案例的分层样本，保持其他条件不变，提高输出上限并同时观察解析成功率、Risk-all及token用量。诊断应作为单独实验，不覆盖当前主表，也不根据表现选择最佳重跑结果。本次尚未运行该追加实验。", "",
        "每模型80个变体实际来自20个物理SCC，每个SCC有4个变体；四模型也共享案例。这里不报告把全部变体当独立样本的显著性。若后续做区间或检验，应按物理SCC成组并保持方法间配对。BGB和Debian仅分别3个、2个物理SCC，分组结论需按描述性结果阅读。", "",
        "## 费用与来源", "",
        f"本轮补跑账本已结算或保守记账 ${verification['budget_ledger_snapshot']['charged_or_assumed_usd']:.6f}，约 **$6.45 / $50**，未结算美元预留为0。Qwen集群推理API费用为0，GPU资源成本未折算美元。历史LEA的按当前冻结单价换算成本不等于历史账单；不能用本轮增量支出宣称三方法的整体成本优势。", "",
        "Qwen已独立核验80例，科学协议与主补跑一致，本地服务路由和部署来源另行保留。用户已向原供应商确认历史Qwen同为AWQ；不将量化精度变化当成事实。历史服务的精确checkpoint版本和默认服务参数未完全核实，跨后端耗时不作公平速度比较。", "",
        "数据文件：`matched_3method_case_metrics.csv`（960条逐例记录）、`matched_3method_summary.csv`（12行主表）、`RESULTS_ANALYSIS.json`（按领域/规模的三方法统计及配对计数）、`verification.json`（统一核验）、`cluster_qwen72b/retrieved_final_20260924/cluster_import_verification.json`（集群导入核验）。", ""]
    (HERE / "RESULTS_ANALYSIS_ZH.md").write_text("\n".join(lines))
    print(json.dumps({"records": len(rows), "paired_cases": 320, "api_calls": 0,
                      "report": str(HERE / "RESULTS_ANALYSIS_ZH.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
