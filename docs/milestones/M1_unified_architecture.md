# Milestone 1: 统一架构

> **目标**: 确定最终 MCGS 变体，合并进 SaMCGSPipeline，消除代码碎片化  
> **预计工时**: 3-5 天  
> **优先级**: P0 — 论文核心架构清晰度  
> **状态**: 🔴 未开始

---

## 1. 现状诊断

### 1.1 四个并行 MCGS 实现

| 变体 | 文件 | 搜索维度 | 核心特性 | 使用位置 |
|------|------|----------|----------|----------|
| **Classic MCGS** | `src/modules/mcgs.py` | 多SCC分支组合 | UCB1, 标准rollout | `SaMCGSPipeline`, `server.py` |
| **AlphaGo MCGS** | `src/modules/alphago_mcgs.py` | 单SCC条款子图 | TT, 虚拟损失, async, Dirichlet噪声 | 实验脚本 |
| **Online Conformal MCGS** | `src/modules/online_conformal_mcgs.py` | 多SCC分支组合 | 运行中分位数检测, OC信号 | 实验脚本 |
| **CVaR MCGS** | `src/modules/cvar_mcgs.py` | 多SCC分支组合 | CVaR惩罚UCB, 尾部感知reward | `compare_plans.py` |

### 1.2 关键不一致

1. **生产管线 vs README**: `SaMCGSPipeline` 和 `server.py` 使用 Classic MCGS, 但 README 宣传 AlphaGo MCGS
2. **接口不统一**: AlphaGo 是 async + 返回 dict; 其他三个是同步 + 返回 list[dict]
3. **模型分裂**: Classic/OC/CVaR 使用 `SearchTree/SCCBranch`; AlphaGo 使用 `NodeStats/EdgeStats/TranspositionEntry`
4. **检测逻辑重复**: OC 的 `_update_detection` 和 AlphaGo 的 `_update_oc` 逻辑高度相似但独立实现

---

## 2. 架构决策

### 2.1 最终架构: 插件化 MCGS 引擎

采用 **策略模式 (Strategy Pattern)** 统一四个变体:

```
BaseMCGS (抽象基类)
├── select(search_tree) -> node, branch     # UCB 选择
├── compute_reward(evaluations) -> float    # 奖励计算
├── backpropagate(path, reward)             # 反向传播
├── post_rollout(rollout_result)            # Rollout 后置钩子 (检测/更新)
└── search(search_tree, dag_results, graph) -> list[dict]  # 统一入口

具体策略:
├── ClassicStrategy    — 标准 UCB1 + max/mean/var reward
├── ConformalStrategy  — UCB1 + OC 检测 (post_rollout 钩子)
├── CVaRStrategy       — CVaR-UCB + 尾部感知 reward
└── AlphaGoAdapter     — 包装 async 搜索, 输出适配为统一 list[dict]
```

### 2.2 配置驱动

```yaml
mcgs:
  mode: "conformal"  # classic | conformal | cvar | alphago
  iterations: 20
  exploration_weight: 1.41
  early_stop_threshold: 0.1
  # conformal-specific
  conformal_alpha: 0.1
  # cvar-specific
  cvar_alpha: 0.9
  risk_lambda: 0.5
  # alphago-specific
  tt_max_reuse: 3
  virtual_loss_weight: 0.5
  dirichlet_alpha: 0.3
```

### 2.3 统一输出格式

所有变体必须输出以下格式:

```python
RolloutResult = {
    "rollout_idx": int,
    "path": list[str],          # SCC evaluation path
    "evaluations": dict,        # clause-level evaluations
    "reward": float,            # scalar reward
    # 可选扩展字段 (由各策略添加)
    "detection": dict | None,   # OC/conformal detection info
    "risk_cost": float | None,  # CVaR risk cost
    "tt_hits": int | None,      # AlphaGo TT hit count
}
```

---

## 3. 实施步骤

### Step 1: 创建 BaseMCGS 抽象基类 (Day 1)

- [ ] 在 `src/modules/` 创建 `base_mcgs.py`
- [ ] 定义 `BaseMCGS` ABC, 包含:
  - `search()` 的统一签名和默认 rollout 循环
  - `_select()`, `_compute_reward()`, `_backpropagate()` 为抽象方法
  - `_post_rollout()` 为可选钩子 (默认 no-op)
- [ ] 提取 Classic MCGS 的 rollout 循环作为基类默认实现

### Step 2: 重构 Classic / OC / CVaR 为策略 (Day 2)

- [ ] 将 `MCGS` 改为继承 `BaseMCGS`, 仅覆写策略方法
- [ ] 将 `OnlineConformalMCGS` 改为继承 `BaseMCGS`:
  - `_select()` 复用 Classic
  - `_post_rollout()` 注入 OC 检测逻辑
- [ ] 将 `CVaRMCGS` 改为继承 `BaseMCGS`:
  - `_select()` 覆写为 CVaR-UCB
  - `_compute_reward()` 覆写为 CVaR-aware reward

### Step 3: AlphaGo 适配器 (Day 3)

- [ ] 创建 `AlphaGoAdapter(BaseMCGS)`:
  - `search()` 内部调用 `AlphaGoMCGS.search()`
  - 将 dict 输出转换为统一 `list[dict]` 格式
  - 提取 per-clause scores → 构造伪 rollout results
- [ ] 保留 `AlphaGoMCGS` 原始实现不动, 只做适配层

### Step 4: 统一 OC 检测模块 (Day 3-4)

- [ ] 将 `OnlineConformalMCGS._update_detection` 和 `AlphaGoMCGS._update_oc` 合并为独立模块 `src/modules/tail_detector.py`
- [ ] 支持 z-score + rank + exceedance 三指标投票
- [ ] 两个 MCGS 变体都引用同一个 `TailDetector` 实例

### Step 5: Pipeline/Server 集成 (Day 4-5)

- [ ] 修改 `SaMCGSPipeline.__init__` 使用工厂模式:
  ```python
  self.mcgs = create_mcgs(config)  # 根据 config["mcgs"]["mode"] 创建
  ```
- [ ] 修改 `server.py` 同步使用相同工厂
- [ ] 修复 `pipeline.py` 中 `run()` 方法的 `on_progress` 签名不一致

### Step 6: 测试验证 (Day 5)

- [ ] 更新 `tests/test_mcgs.py` 覆盖所有四个模式
- [ ] 运行 smoke test 确保所有模式输出格式一致
- [ ] 验证现有实验脚本在新架构下仍可运行

---

## 4. 论文呈现方案

统一后的架构在论文中呈现为:

> **Section 3.7: MCGS Search Engine**
> 
> SA-MCGS 的搜索引擎采用可插拔策略架构。默认使用 **Conformal MCGS** 策略,
> 结合标准 UCB1 选择与在线尾部检测, 实现风险信号的统计校准。
> 我们同时实现了 CVaR-aware 和 AlphaGo-style 变体作为 ablation 对比。
>
> 这一统一架构为后续在 **CLAUSE (EACL 2026)** 权威 Benchmark 上的对标实验提供了核心引擎支持 (见 Milestone 2)。

**Ablation 对比表** (将在 M1 完成后可执行):

| 搜索策略 | Reward 类型 | 检测机制 | 特殊功能 | 对标 Baseline |
|----------|------------|---------|---------|--------------|
| Classic | max/mean/var | 无 | Baseline | Direct LLM |
| Conformal (默认) | max/mean/var | OC 尾部检测 | 统计校准 | CLAUSE Baselines |
| CVaR | CVaR/max/mean | 无 | 尾部风险敏感 | - |
| AlphaGo | Per-clause | OC | TT + 虚拟损失 | LATS |

---

## 5. 验收标准

- [ ] `config["mcgs"]["mode"]` 可切换四种模式, 无需改代码
- [ ] 所有模式的 `search()` 返回统一 `list[dict]` 格式
- [ ] `Aggregator` 和 `RiskIdentifier` 无需感知具体模式
- [ ] `server.py` 和 `SaMCGSPipeline` 使用相同工厂
- [ ] OC 检测逻辑只有一份实现
- [ ] 所有现有测试通过
- [ ] README 与实际代码一致
