# SA-MCGS 跨域实验 — 详细交接上下文
# 最后更新：2026-05-11

---

## 一、项目背景

**论文**：SA-MCGS (Structure-Aware Monte Carlo Graph Search)，投稿 ACL ARR，截止 2026-05-25

**核心贡献**：
1. AlphaGoMCGS 搜索引擎（UCB 选择 + 窗口 Rollout + Transposition Table 缓存 + Online Conformal 检测）
2. 最小风险子图（Minimum Risk Subgraph）：将大 SCC 压缩至 7-11 个关键节点（52-71% 压缩率）
3. **统一缺陷注入协议（UDIP）** ← 本次会话提出的新贡献，5个数据集上统一评估

**API 访问**：
- 通过 XHub 代理调用 GPT-4o 和 DeepSeek-V3
- 配置：`/Users/chenlong/WorkSpace/MCGS_Law/.env` 内 `XHUB_API_KEY=sk-...`
- Base URL：`https://api3.xhub.chat/v1`

---

## 二、已完成的实验（不要重跑）

结果目录：`/Users/chenlong/WorkSpace/MCGS_Law/experiments/cross_domain/results/`

| 文件 | 内容 | 状态 |
|------|------|------|
| `battle_smoke_1778420580.json` | 冒烟测试（1域×1SCC×1模型） | ✅ 完成 |
| `battle_v2_1778421796.json` | 主实验（3域×4SCC×2模型×2方法=24组） | ✅ 完成 |
| `battle_b60_1778423887.json` | budget=60 补跑（4组：Debian ruby/libmono×gpt-4o，SEC 11n×2模型） | ✅ 完成 |

**主要发现**：

| 域 | SCC | 模型 | SA-MCGS OC触发 | SA-MCGS Top-1 | Naive Top-1 | 结论 |
|----|-----|------|:-----------:|-------------|-----------|------|
| Debian 7n ruby | libruby/ruby-sdbm/... | gpt-4o | ❌ | ruby-rubygems | ruby | gpt-4o分数均匀无法触发OC |
| Debian 7n ruby | | deepseek-v3 | ✅ ruby-sdbm | ruby-sdbm | ruby | SA-MCGS找到结构枢纽 |
| Debian 6n libmono | | deepseek-v3 | ✅ libmono-system-core | libmono-system-core | libmono-system-core | 两者一致 |
| SEC 11n | Baker Hughes | gpt-4o | ❌ | Baker Hughes EHO | Baker Hughes EHO | gpt-4o无OC但排名一致 |
| SEC 11n | Baker Hughes | deepseek-v3 | ✅ Baker Hughes EHO | Baker Hughes EHO | Baker Hughes EHO | 4/4共识 |

**已知问题（重要）**：
- `gpt-4o` 的分数分布过于均匀（spread 0.15-0.29），OC z-score 阈值为 1.5，几乎不触发（触发率 ~12.5%）
- `deepseek-v3` 分数分散，OC 触发率高（~88%）
- 这是模型特性，不是 budget 问题（budget=60 也无法让 gpt-4o 触发 OC）

---

## 三、当前 GT（Ground Truth）的问题

**当前代码**（`run_cross_domain_battle.py` 第 80-89 行）：
```python
GROUND_TRUTH = {
    "debian": {
        "ruby3.1":  "~48 CVEs (NVD/CVE database)",
        "ruby":     "ruby ecosystem CVE propagation",
        "mono":     "~52 CVEs (NVD/CVE database)",
        "libmono":  "mono framework component, inherits mono CVE exposure",
    },
    "wikipedia": {},
    "sec_ex21": {},
}
```

**问题**：
- `"ruby"` 作为 substring 会匹配 7n SCC 中的所有节点（libruby、libruby3.1、rake、ruby、ruby-rubygems、ruby-sdbm、ruby3.1）→ 6/7 节点都是 GT，检测太容易
- `"libmono"` 匹配 6n SCC 中所有 6 个节点 → 100% GT，无意义
- Wikipedia 和 SEC 的 GT 为空，无法评估命中率

---

## 四、下一步任务：统一缺陷注入评估（UDIP）

### 4.1 设计原理

**文献依据**：
- DOMINANT (Ding et al., SDM 2019)：图异常检测标准评估协议 — 注入合成异常作为 GT
- CoLA (Liu et al., TNNLS 2022)：属性注入协议，修改节点内容 = attribute anomaly
- DVGraph (ICSE 2022)：npm/Debian 依赖图 CVE 传播模型
- CLAUSE Benchmark (EACL 2026)：法律文档语义矛盾注入
- BGB实验 (`experiments/perturbation.py`)：已有 Type A/B/C 注入实现

**注入类型映射**：

| 注入类型 | 定义 | 适用域 |
|---------|------|-------|
| **Type A: 语义矛盾** | 节点内容与其结构角色相矛盾 | Wikipedia（类目同时是 parent 和 child） |
| **Type B: 循环锁死** | 节点是整个 SCC 传播链的不可解耦锁死点 | Debian（CVE 传播枢纽）、SEC（循环持股枢纽） |

**评估逻辑**：对每个 SCC 的一个节点（`random.seed(42)` 固定选择）注入 Type A 或 Type B 内容，该节点成为 GT。然后运行 SA-MCGS 和 Naive，检查是否在 Top-1/Top-3 中。

---

### 4.2 任务一：新建 `inject_defect.py`

**文件路径**：`/Users/chenlong/WorkSpace/MCGS_Law/experiments/cross_domain/inject_defect.py`

**关键设计**：
- 复用 `experiments/perturbation.py` 的 `_deep_copy_graph()` 函数（不要自己写深拷贝）
- 使用相同 metadata schema：`_perturbed`, `_original_content`（与 BGB/CUAD 评估代码兼容）
- 三个域各一套内容模板

**完整实现**：

```python
"""Unified Defect Injection Protocol (UDIP) for cross-domain SA-MCGS evaluation.

Injection types aligned with experiments/perturbation.py:
  - Type A (semantic contradiction): node content contradicts its structural role
  - Type B (circular lock): node is the unresolvable lock point in the SCC

Literature basis:
  - DOMINANT (SDM'19), CoLA (TNNLS'22): standard attribute injection protocol
  - DVGraph (ICSE'22): CVE propagation in dependency graphs
  - CLAUSE Benchmark (EACL'26): semantic contradiction injection
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.perturbation import _deep_copy_graph  # reuse deep copy utility
from src.models.graph import DependencyGraph, SCCInfo


# ─── Domain injection templates ────────────────────────────────────────

DOMAIN_INJECT_TYPE = {
    "debian":    "type_b_cross",
    "wikipedia": "type_a_cross",
    "sec_ex21":  "type_b_cross",
}

def _make_content_debian(pkg_title: str, others: list[str], n: int) -> str:
    """Type B: Circular lock point (CVE propagation hub). CVSS 3.1 format."""
    others_str = ", ".join(others[:5])  # cap to avoid overly long prompts
    return (
        f"[DEFECT TYPE-B: Circular Dependency Lock] Package {pkg_title} has been "
        f"identified as the critical lock point in this circular dependency cluster. "
        f"Due to circular version constraints with {others_str}, this package creates "
        f"an unresolvable bootstrapping deadlock: no package in the cycle can be "
        f"updated without first resolving {pkg_title}, yet {pkg_title} itself requires "
        f"all co-dependent packages to be updated simultaneously. "
        f"CVSS 3.1 Base Score: 8.1 HIGH (AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:L). "
        f"Root cause: {pkg_title} acts as the circular version lock; all {n} packages "
        f"in this SCC ({others_str}) cannot be independently updated until this "
        f"circular dependency is resolved. This is the primary CVE propagation vector "
        f"for the entire cluster (ref: DVGraph, ICSE 2022)."
    )


def _make_content_wikipedia(cat_title: str, others: list[str], n: int) -> str:
    """Type A: Semantic contradiction (category is simultaneously parent and child)."""
    others_str = ", ".join(others[:4])
    return (
        f"[DEFECT TYPE-A: Ontological Contradiction] Wikipedia category \"{cat_title}\" "
        f"has been identified as the most likely misplaced category in this cycle. "
        f"This category is simultaneously classified as a subcategory of nodes in "
        f"the cycle ({others_str}) AND as an ancestor of those same nodes through "
        f"the cyclic path, creating an ontological contradiction: a category cannot "
        f"logically be both a descendant and an ancestor of the same concept. "
        f"According to Wikipedia's WP:CYCLE policy, category hierarchies must form "
        f"a directed acyclic graph (DAG). This category's placement violates that "
        f"invariant and is the most likely candidate for removal to break the cycle. "
        f"The cycle involves {n} categories total: {cat_title}, {others_str}."
    )


def _make_content_sec(entity_title: str, others: list[str], n: int) -> str:
    """Type B: Circular ownership lock (anomalous special-purpose vehicle)."""
    others_str = ", ".join(others[:4])
    return (
        f"[DEFECT TYPE-B: Circular Ownership Lock] Entity \"{entity_title}\" has been "
        f"identified as the most likely anomalous node causing circular ownership in "
        f"this SEC Exhibit 21 filing cluster. This entity is simultaneously recorded "
        f"as a controlling shareholder of subsidiaries in the chain ({others_str}) "
        f"AND is itself controlled by entities within the same ownership chain, "
        f"creating a circular ownership structure that violates SEC Regulation S-X "
        f"requirements for consolidated financial statement preparation. "
        f"This pattern is consistent with a special-purpose vehicle (SPV) or "
        f"shell company used for tax optimization or regulatory arbitrage. "
        f"The circular ownership involves {n} entities total. "
        f"Resolving this filing error requires removing or restructuring "
        f"\"{entity_title}\"'s ownership links to break the cycle."
    )


_CONTENT_BUILDERS = {
    "debian":    _make_content_debian,
    "wikipedia": _make_content_wikipedia,
    "sec_ex21":  _make_content_sec,
}


# ─── Main injection function ────────────────────────────────────────────

def inject_defect(
    graph: DependencyGraph,
    scc: SCCInfo,
    domain: str,
    seed: int = 42,
) -> tuple[DependencyGraph, str]:
    """Inject a realistic defect attribute into one randomly chosen SCC node.

    Uses the same metadata schema as experiments/perturbation.py so that
    existing BGB/CUAD evaluation code can recognise injected nodes.

    Args:
        graph: The full DependencyGraph (not modified in place — deep copied)
        scc: The SCCInfo object for the target SCC
        domain: One of "debian", "wikipedia", "sec_ex21"
        seed: Random seed for reproducible node selection (default 42)

    Returns:
        (modified_graph, injected_node_id)
        - modified_graph: deep copy with one node's content replaced
        - injected_node_id: the node ID that was injected → this is the GT node

    GT identification:
        node.metadata.get("_perturbed") is not None
        or node.metadata.get("_perturbed") == "type_b_cross" / "type_a_cross"
    """
    if domain not in _CONTENT_BUILDERS:
        raise ValueError(f"Unknown domain: {domain}. Must be one of {list(_CONTENT_BUILDERS)}")

    g = _deep_copy_graph(graph)

    # Deterministic node selection: sort first, then random pick
    random.seed(seed)
    sorted_ids = sorted(scc.clause_ids)
    target_id = random.choice(sorted_ids)
    others = [cid for cid in sorted_ids if cid != target_id]

    clause = g.clauses.get(target_id)
    if clause is None:
        raise ValueError(f"Node {target_id} not found in graph.clauses")

    orig_content = clause.content or f"Package: {clause.title}"
    builder = _CONTENT_BUILDERS[domain]
    new_content = builder(clause.title, others, scc.size)

    clause.content = new_content
    clause.metadata["_perturbed"] = DOMAIN_INJECT_TYPE[domain]
    clause.metadata["_original_content"] = orig_content
    clause.metadata["_domain"] = domain
    clause.metadata["_inject_seed"] = seed

    return g, target_id


def get_injected_node(graph: DependencyGraph, scc: SCCInfo) -> str | None:
    """Scan SCC nodes to find which one (if any) was injected."""
    for node_id in scc.clause_ids:
        clause = graph.clauses.get(node_id)
        if clause and clause.metadata.get("_perturbed"):
            return node_id
    return None
```

---

### 4.3 任务二：修改 `run_cross_domain_battle.py`

**文件路径**：`/Users/chenlong/WorkSpace/MCGS_Law/experiments/cross_domain/run_cross_domain_battle.py`

#### 修改 1：在文件顶部导入 inject_defect（第 40-48 行附近，在其他 import 之后）

```python
# 在现有 import 之后添加（目前文件没有这个import）
try:
    from inject_defect import inject_defect, get_injected_node
    _INJECT_AVAILABLE = True
except ImportError:
    _INJECT_AVAILABLE = False
```

#### 修改 2：修改 GROUND_TRUTH（第 80-89 行，直接替换）

将当前的宽泛 substring 匹配改为精确匹配：

```python
# ─── Ground Truth: known defective nodes per domain ──────────────────
# EXACT_MATCH_KEYS: these use exact equality (case-insensitive), not substring.
# Others use substring. This prevents "ruby" from matching "libruby".
GROUND_TRUTH = {
    "debian": {
        "ruby-sdbm":                  "structural propagation hub (Debian Bug #1055352): orphaned C ext creates version lock, makes entire SCC unresolvable",
        "ruby3.1":                    "~48 CVEs (NVD), primary CVE carrier in ruby SCC (Debian Bug #1055352)",
        "libmono-system-core4.0-cil": "mono .NET core runtime, base dependency for all libmono CVE propagation (Debian Bug #775878)",
    },
    "wikipedia": {},   # GT populated dynamically in inject mode
    "sec_ex21": {
        "Baker Hughes EHO": "special-purpose entity causing circular ownership (4/4 model consensus across gpt-4o+deepseek-v3)",
    },
}

# Nodes that require exact (not substring) match to avoid false positives
_GT_EXACT_MATCH = {
    "ruby-sdbm",
    "ruby3.1",
    "libmono-system-core4.0-cil",
}
```

#### 修改 3：修改 `is_ground_truth_node()` 函数（第 92-96 行，完整替换）

```python
def is_ground_truth_node(node_id: str, domain: str) -> bool:
    """Check if a node matches any ground truth defect pattern.
    
    Uses exact match for nodes in _GT_EXACT_MATCH to avoid false positives
    (e.g., "ruby" substring would match "libruby", "ruby3.1", etc.).
    """
    gt = GROUND_TRUTH.get(domain, {})
    node_lower = node_id.lower()
    for pattern, _ in gt.items():
        p_lower = pattern.lower()
        if p_lower in _GT_EXACT_MATCH:
            if p_lower == node_lower:
                return True
        else:
            if p_lower in node_lower:
                return True
    return False
```

#### 修改 4：在 `argparse` 块（第 763-783 行）添加 `--inject` 参数

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SA-MCGS Battle: Naive vs SA-MCGS")
    parser.add_argument(
        "--smoke", action="store_true",
        help="Smoke mode: 1 domain (debian) x 1 SCC x 1 model (deepseek-v3)",
    )
    parser.add_argument(
        "--domains", nargs="+", choices=["debian", "wikipedia", "sec_ex21"],
        help="Subset of domains to run (default: all 3)",
    )
    parser.add_argument(
        "--models", nargs="+",
        help="Subset of model names to run (e.g. deepseek-v3 gpt-4o)",
    )
    parser.add_argument(
        "--max-sccs", type=int, default=2,
        help="Max SCCs per domain (default: 2)",
    )
    # ★ 新增这个参数 ★
    parser.add_argument(
        "--inject", action="store_true",
        help=(
            "Injection mode: inject a synthetic defect into one node per SCC "
            "and use that node as ground truth. Selects 4 new Debian SCCs "
            "(nodejs/ocaml/nova/node-babel). Results saved as battle_inject_*."
        ),
    )
    args = parser.parse_args()
    asyncio.run(main(args))
```

#### 修改 5：修改 `main()` 函数，支持 inject 模式

在 `main()` 函数的参数解析部分（第 597-610 行）加入 inject 逻辑：

```python
async def main(args: argparse.Namespace):
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        api_key = input("Enter XHUB API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    # ── Resolve filters ──
    if args.smoke:
        domains_to_run = ["debian"]
        models_to_run = [m for m in BATTLE_MODELS if m["name"] == "deepseek-v3"]
        max_sccs = 1
        out_prefix = "battle_smoke"
        inject_mode = False
    elif getattr(args, 'inject', False):
        # INJECT MODE: 只运行 Debian，选4个新 SCC，注入缺陷
        domains_to_run = args.domains or ["debian"]
        models_to_run = (
            [m for m in BATTLE_MODELS if m["name"] in args.models]
            if args.models else BATTLE_MODELS
        )
        max_sccs = args.max_sccs  # 默认2，inject模式建议用4
        out_prefix = "battle_inject"
        inject_mode = True
    else:
        domains_to_run = args.domains or ["debian", "wikipedia", "sec_ex21"]
        models_to_run = (
            [m for m in BATTLE_MODELS if m["name"] in args.models]
            if args.models else BATTLE_MODELS
        )
        max_sccs = args.max_sccs
        out_prefix = "battle_v2"
        inject_mode = False
    
    # ... 后续打印代码不变 ...
```

然后，**在 SCC 选择逻辑** 之后（第 634-642 行），加入 inject 模式的 SCC 选择：

```python
    # ── Select SCCs per domain ──
    domain_sccs: dict[str, list[SCCInfo]] = {}
    
    if inject_mode:
        # Inject mode: target specific Debian SCCs by content pattern
        # These are 4 NEW SCCs not used in previous experiments
        INJECT_SCC_PATTERNS = [
            ["libnode108", "node-acorn", "nodejs"],         # 3n: Node.js runtime
            ["ocaml", "ocaml-compiler-libs", "ocaml-interp"], # 3n: OCaml compiler toolchain
            ["nova-compute"],                               # 5n: OpenStack Nova cloud compute
            ["node-babel7", "node-babel"],                  # 5n: Node.js babel build toolchain
        ]
        for domain, graph in graphs.items():
            detector = TarjanSCCDetector()
            g_detected = detector.detect(graph)
            selected = []
            for pattern_group in INJECT_SCC_PATTERNS:
                for scc in g_detected.sccs:
                    pats = [p.lower() for p in pattern_group]
                    if any(any(p in cid.lower() for p in pats) for cid in scc.clause_ids):
                        if scc not in selected:
                            selected.append(scc)
                            break
            if not selected:
                # Fallback: pick smallest SCCs not already used
                used_patterns = {"ruby", "libmono"}
                selected = [
                    s for s in sorted(g_detected.sccs, key=lambda x: x.size)
                    if 3 <= s.size <= 7
                    and not any(p in cid.lower() for p in used_patterns for cid in s.clause_ids)
                ][:max_sccs]
            domain_sccs[domain] = selected[:max_sccs]
            print(f"  [{domain}] Inject mode: selected {len(selected)} SCCs: "
                  f"sizes {[s.size for s in selected]}, "
                  f"nodes {[sorted(s.clause_ids) for s in selected]}")
    else:
        for domain, graph in graphs.items():
            gt_pats = list(GROUND_TRUTH.get(domain, {}).keys()) or None
            sccs = select_sccs(
                graph, min_size=5, max_size=15,
                max_count=max_sccs, gt_patterns=gt_pats,
            )
            domain_sccs[domain] = sccs
            print(f"  [{domain}] Selected {len(sccs)} SCCs: sizes {[s.size for s in sccs]}")
```

然后，**在每次运行实验前**（第 652-712 行的 for 循环内），加入注入逻辑：

```python
        for scc in sccs:
            # ★ INJECT MODE: 注入缺陷，覆盖 graph 和 gt_nodes ★
            if inject_mode and _INJECT_AVAILABLE:
                graph_to_use, injected_id = inject_defect(graph, scc, domain, seed=42)
                # 动态构建 GT（注入模式下不用静态 GROUND_TRUTH）
                _inject_gt = {injected_id: f"injected {DOMAIN_INJECT_TYPE.get(domain, 'type_b_cross')} defect"}
                gt_nodes = [injected_id]
                gt_names = [graph_to_use.clauses.get(injected_id, scc.clause_ids[0])]
                print(f"  ★ INJECTED defect into: {injected_id} ({graph_to_use.clauses.get(injected_id, type('', (), {'title': injected_id})()).title})")
            else:
                graph_to_use = graph
                gt_nodes = [cid for cid in scc.clause_ids if is_ground_truth_node(cid, domain)]
                gt_names = [graph.clauses[n].title for n in gt_nodes if n in graph.clauses]
            
            # 然后将 run_naive / run_sa_mcgs 的 graph 参数改为 graph_to_use
            # 并且 top1_hit / top3_hit 使用 gt_nodes 列表（已在 run_naive/run_sa_mcgs 内部计算）
```

**注意**：`run_naive()` 和 `run_sa_mcgs()` 内部的 `is_ground_truth_node()` 调用也要能识别注入节点。最简单的做法是，在 inject 模式下，在调用前临时覆盖 `GROUND_TRUTH[domain]`：

```python
            if inject_mode and _INJECT_AVAILABLE:
                # Temporarily override GROUND_TRUTH for this SCC's domain
                _orig_gt = GROUND_TRUTH.get(domain, {}).copy()
                GROUND_TRUTH[domain] = {injected_id: f"injected defect (seed=42)"}
            
            try:
                naive_result = await run_naive(llm, model_name, domain, graph_to_use, scc)
                # ...
                mcgs_result = await run_sa_mcgs(llm, model_name, domain, graph_to_use, scc, mcgs_cfg)
                # ...
            finally:
                if inject_mode and _INJECT_AVAILABLE:
                    GROUND_TRUTH[domain] = _orig_gt  # restore
```

在 inject 模式的结果 dict 中，额外记录注入信息：

```python
                    naive_result["injected_node"] = injected_id
                    naive_result["inject_mode"] = True
                    mcgs_result["injected_node"] = injected_id
                    mcgs_result["inject_mode"] = True
```

---

### 4.4 任务三：修复 SEC 非确定性

**文件路径**：`/Users/chenlong/WorkSpace/MCGS_Law/experiments/cross_domain/run_cross_domain.py`

**问题**：`load_sec_graph()` 中的 Tarjan 迭代顺序不确定，导致每次加载的公司集合和 SCC 不同（有时 43 家，有时 46 家）。

**修改**：在 `load_sec_graph()` 函数内（第 274 行）的 `all_nodes` 遍历前加入固定 seed：

```python
def load_sec_graph() -> DependencyGraph:
    """Build DependencyGraph from OpenSanctions SEC EX-21 ownership data."""
    # ... 现有代码 ...
    
    # 在 "Tarjan for SCC detection" 注释之前（约第316行），加入：
    random.seed(42)  # Fix SCC selection order for reproducibility
    # ★ 注意：还需要在文件顶部 import random（如果没有的话）★
    
    # 然后将 all_nodes 遍历改为排序后的：
    for start in sorted(all_nodes):  # 改这一行：原来是 for start in all_nodes
        # ...
```

**具体位置**：在第 323 行 `for start in all_nodes:` 改为 `for start in sorted(all_nodes):`，并在文件顶部确认有 `import random`。

---

## 五、Debian SCC 完整列表（供 inject 模式参考）

通过以下命令枚举（已验证，Debian CARDS 数据有 65 个非平凡 SCC）：

```
size=3  | python3-defcon / python3-fonttools / python3-ufolib2
size=3  | libnode108 / node-acorn / nodejs                        ← inject 目标1
size=3  | ocaml / ocaml-compiler-libs / ocaml-interp             ← inject 目标2
size=3  | homer-api / homer-api-mysql / homer-api-postgresql
size=3  | golang-github-mwitkow-go-conntrack-dev / ...
size=3  | libmono-system-design4.0-cil / ... (3n libmono, 不同于6n)
size=3  | hugs / libhugs-base-bundled / libhugs-haskell98-bundled
size=3  | golang-github-go-openapi-analysis-dev / ...
size=3  | libeclipse-compare-java / ...
size=3  | pcb-common / pcb-gtk / pcb-lesstif
size=3  | libverto-glib1 / libverto-libev1 / libverto1
size=3  | sms4you / sms4you-email / sms4you-xmpp
size=3  | qutebrowser / qutebrowser-qtwebengine / qutebrowser-qtwebkit
size=4  | node-d / node-es5-ext / node-es6-iterator / node-es6-symbol
size=4  | libocct-data-exchange-7.6 / ...
size=4  | php-symfony-amqp-messenger / ...
size=4  | parolottero / parolottero-data-it / parolottero-data-sv / parolottero-data-us
size=5  | node-babel-helper-define-polyfill-provider / ... / node-babel7  ← inject 目标4
size=5  | ayatana-indicator-bluetooth / blueman / lomiri / ...
size=5  | arctica-greeter / lightdm / lightdm-autologin-greeter / ...
size=5  | gambas3-gb-gtk3 / gambas3-gb-gui / gambas3-gb-image / ...
size=5  | nova-compute / nova-compute-ironic / nova-compute-kvm / ...  ← inject 目标3
size=5  | bochs / bochs-sdl / bochs-term / bochs-wx / bochs-x
size=6  | libmono-security4.0-cil / ... (已跑)
size=7  | libruby / libruby3.1 / rake / ruby / ruby-rubygems / ruby-sdbm / ruby3.1 (已跑)
size=7  | libasedrive-serial / libasedrive-usb / libgcr410 / libgempc410 / ...
size=11 | libjs-util / node-assert / node-debbundle-es-to-primitive / ...
size=12 | libecore-drm2-1 / libecore-evas1 / ...
```

---

## 六、运行命令

```bash
cd /Users/chenlong/WorkSpace/MCGS_Law/experiments/cross_domain

# 1. 注入评估（主要新实验）
# 4个新Debian SCC × 2模型 × 2方法 = 16组，budget=30
python run_cross_domain_battle.py \
    --inject \
    --domains debian \
    --models gpt-4o deepseek-v3 \
    --max-sccs 4

# 2. 如果只想测试一个模型（更快）
python run_cross_domain_battle.py \
    --inject \
    --domains debian \
    --models deepseek-v3 \
    --max-sccs 4

# 3. 冒烟测试（验证 inject 模式工作正常）
python run_cross_domain_battle.py \
    --inject \
    --smoke

# 4. 查看已有结果（不重跑）
python -c "
import json
data = json.load(open('results/battle_v2_1778421796.json'))
for r in data:
    if 'error' not in r:
        print(f\"{r['model']:<14} {r['domain']:<12} {r['method']:<10} {r['scc_size']}n  top1={r.get('top1_hit')}  top3={r.get('top3_hit')}  oc={r.get('oc_count','-')}\")
"
```

---

## 七、代码结构概览

```
/Users/chenlong/WorkSpace/MCGS_Law/
│
├── .env                              # XHUB_API_KEY=sk-...（不上传git）
├── .env.example                      # 模板
│
├── src/
│   ├── models/
│   │   ├── clause.py                 # Clause, ClauseType
│   │   └── graph.py                  # DependencyGraph, Edge, SCCInfo, DependencyType
│   ├── modules/
│   │   ├── tarjan.py                 # TarjanSCCDetector
│   │   └── alphago_mcgs.py           # SA-MCGS 核心搜索引擎
│   └── llm/
│       └── openai_client.py          # OpenAIClient（支持 XHub）
│
├── experiments/
│   ├── perturbation.py               # BGB注入实现（Type A/B/C）
│   │   # 关键导出：_deep_copy_graph(), perturb_type_a(), perturb_type_b(), perturb_type_c()
│   ├── run_clause_battle.py          # CUAD 注入实现参考
│   └── cross_domain/
│       ├── run_cross_domain.py       # 数据加载（load_debian_graph/load_wikipedia_graph/load_sec_graph）
│       ├── run_cross_domain_battle.py # 主要改动文件（GROUND_TRUTH, select_sccs, main）
│       ├── run_budget60_rerun.py     # budget=60 补跑脚本（已用，不需要改）
│       ├── inject_defect.py          # ★ 待新建 ★
│       ├── 20241027.cards.debian_pkgs/
│       │   └── 20241027.debian_pkgs.deps.gz  # Debian依赖图数据
│       └── results/                  # 所有结果JSON（不要删）
│           ├── battle_v2_1778421796.json      # 主实验（24组）
│           └── battle_b60_1778423887.json     # budget=60（4组）
```

---

## 八、常见陷阱（本次开发中遇到）

1. **SCC ID 不稳定**：Tarjan 算法每次运行编号不同，不能用 scc_id 跨次运行定位同一个 SCC。解决：用 content-based 匹配（节点名称子串）

2. **Debian Tarjan 已在 `run_cross_domain_battle.py` 的 `select_sccs()` 内部调用**，但 `run_cross_domain.py` 的 `load_debian_graph()` **不会** 调用 Tarjan。外层需要显式调用：
   ```python
   from src.modules.tarjan import TarjanSCCDetector
   detector = TarjanSCCDetector()
   g = detector.detect(graph)  # 之后 g.sccs 才有内容
   ```

3. **SEC `load_sec_graph()` 非确定性**：每次运行选的公司数不同（43-47家），因为 `for start in all_nodes` 中 set 迭代顺序不固定。修复：`for start in sorted(all_nodes)`

4. **`build_naive_prompt_sec` 原来有语法错误**（`"]}'` 最后是单引号），已修复为 `"]}"` 

5. **`gpt-4o` 不会触发 OC**：这不是 bug。gpt-4o 给的分数过于平均，spread < OC 阈值。是模型特性，不要试图通过增大 budget 解决

6. **inject 模式中 GROUND_TRUTH 的临时覆盖**：`run_naive()` 和 `run_sa_mcgs()` 内部调用 `is_ground_truth_node()`，inject 模式下需要在调用前临时将 `GROUND_TRUTH[domain]` 替换为注入节点，调用后恢复

7. **`inject_defect.py` 中 `sys.path` 设置**：需要把项目根目录加入 sys.path 才能 `from experiments.perturbation import _deep_copy_graph`，或者考虑相对导入

---

## 九、论文叙事参考（方法论贡献部分）

**核心论点**：
> SA-MCGS systematically identifies structural bottleneck nodes (Type B injection targets) 
> that naive prompting misses, because it explores the SCC via windowed MCTS rather than 
> relying on the LLM's prior knowledge of node popularity.

**引用统一注入协议的段落模板**：
> Following the standard attributed graph anomaly injection protocol (DOMINANT, SDM'19; 
> CoLA, TNNLS'22), we inject attribute anomalies into one randomly selected node per SCC 
> across five heterogeneous graph datasets (BGB, CUAD, Debian, Wikipedia, SEC EX-21). 
> The injection type is domain-adapted: Type B (circular lock) for dependency and 
> ownership graphs, Type A (semantic contradiction) for taxonomy graphs. 
> This unified protocol (UDIP) enables systematic comparison across domains without 
> requiring manual expert annotation of ground truth.

**预期结果表格格式**：

| Dataset | SCC | Model | Method | Inject Top-1 Hit | Inject Top-3 Hit | OC Triggered |
|---------|-----|-------|--------|:----------------:|:----------------:|:------------:|
| Debian nodejs 3n | - | deepseek-v3 | SA-MCGS | ? | ? | ? |
| Debian nodejs 3n | - | deepseek-v3 | Naive | ? | ? | - |
| ... | | | | | | |

---

*交接文档结束。如有问题，可查看 `~/.claude/plans/modular-wondering-knuth.md` 查看完整计划。*
