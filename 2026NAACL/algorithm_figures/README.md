# LFP-MCGS 算法流程图

本目录把 LFP-MCGS 的总体架构、八个内部模块和一次完整动态演算拆成三组视觉材料。所有图同时提供 SVG 矢量源和 PNG 预览；动态过程同时提供可播放 HTML、GIF 和八张独立关键帧。

## 1. 总体架构

- [`01_overall_architecture.svg`](./01_overall_architecture.svg)：适合论文、幻灯片继续编辑的矢量图。
- [`01_overall_architecture.png`](./01_overall_architecture.png)：快速预览版本。

从左到右阅读：

1. 自然语言 records 与 query 构成高召回 candidate dependency graph；
2. Tarjan SCC 只定位 recursive region，不产生任何逻辑事实；
3. proof obligations、coverage 与 MCGS statistics 决定下一窗口；
4. LLM 只输出 candidate facts / rules，首先进入可修改的 `L_t`；
5. validation gate 通过后才进入只增不减的 `Fhat_t / Rhat_t`；
6. deterministic incremental LFP engine 更新 `K_t / ΔK_t / Pi_t`；
7. `ΔK` 与 missing premises 反馈给 scheduler，改变下一窗口的选择价值；
8. 算法区分 verified entailment、coverage-certified not-entailment 和 budget-limited unresolved。

最关键的边界是：

```text
LLM proposes
    → validator commits
        → deterministic engine derives
            → MCGS schedules the next read
```

LLM 没有任何直接写入 closure `K` 的通道。

## 2. 八模块组合大图

- [`02_module_atlas.svg`](./02_module_atlas.svg)：八个内部模块组合矢量图。
- [`02_module_atlas.png`](./02_module_atlas.png)：高分辨率预览。

八个面板分别解释：

- A：rule dependency graph、SCC condensation DAG、closure-state lattice 的区别；
- B：proof-obligation-driven UCB window selection；
- C：local LLM parsing、static parse cache 与 closure-state transposition；
- D：candidate ledger、validation gate 与 monotonic commit；
- E：atom agenda、`uses[a]`、rule readiness 与增量 LFP；
- F：`ΔK` 如何只唤醒相关 rules / producer windows；
- G：不同读取顺序的 transposition 合并，以及不能丢失的 provenance；
- H：proof core 与三种终止状态。

## 3. 动态演算

- [`03_dynamic_walkthrough.html`](./03_dynamic_walkthrough.html)：可逐步、拖动或自动播放。
- [`03_dynamic_walkthrough.gif`](./03_dynamic_walkthrough.gif)：循环播放版本。
- [`03_keyframes_contact_sheet.svg`](./03_keyframes_contact_sheet.svg)：八帧纵览矢量图。
- [`03_keyframes_contact_sheet.png`](./03_keyframes_contact_sheet.png)：八帧纵览预览。
- [`keyframes/`](./keyframes/)：每一帧的独立 SVG 与 PNG。

动态例子使用以下 canonical program；实际算法输入仍是对应的自然语言 records：

```text
d1: Anchor(Alice)
d2: Clear(Alice)
r1: Anchor(x) → Ready(x)
r2: Ready(x) ∧ Clear(x) → Approved(x)
r3: Approved(x) → Certified(x)
r4: Certified(x) → Ready(x)          # closing rule
q : Certified(Alice)
```

`{Ready, Approved, Certified}` 构成 recursive SCC。`r4` 可以在 `Certified(Alice)` 已被推出以后回到 `Ready(Alice)`，但不能在没有外部 seed 时启动这个环。

| 帧 | 发生的事情 | 状态变化 |
|---:|---|---|
| 0 | 输入还是自然语言；初始化 query frontier | `Fhat=Rhat=K=∅` |
| 1 | query-backward 选择 `Wq={r3,r4}` | 只改变调度状态 |
| 2 | r3/r4 验证并提交；循环没有 fact 可启动 | `Rhat={r3,r4}`, `K=∅` |
| 3 | 找到 r2 与 `Clear(Alice)` | `ΔK={Clear(Alice)}`，仍缺 Ready |
| 4 | 沿 missing premise 找到 r1 | r1 已提交，但仍缺 Anchor seed |
| 5 | 提交 `Anchor(Alice)`；同一次 saturation 中 r1 推出 Ready | `ΔK={Anchor,Ready}` |
| 6 | r2、r3 连续 firing 到达 query；r4 的 head 已知 | verified entailment + grounded proof |
| 7 | 将 seed 换为 `Anchor(Bob)` | Alice 的循环仍未启动；coverage-certified not-entailment |

Frame 5–6 是**同一次 deterministic saturation 的内部微步**，不是每推导一个 atom 就调用一次 LLM。

## 视觉图例

- 蓝色：输入结构或已进入 closure 的事实；
- 紫色：MCGS 调度、SCC 边界与 transposition；
- 橙色：尚未确认的 LLM candidates；
- 绿色：已验证、可参与逻辑求值的程序与 proof；
- 青色：当前 `ΔK` 和增量 agenda；
- 红色虚线：阻塞、拒绝或不能作为 grounded support 的循环路径；
- 灰色：未访问文本、缓存或中性统计。

## 语义检查清单

这些图有意避免以下常见误画：

1. Candidate rule 不能在 validation 前 firing；
2. proof obligation 是调度信息，不是逻辑事实；
3. SCC 是规则/谓词依赖结构，closure-state graph 仍然单调向前；
4. conjunction 必须满足完整 body，不能只满足一个 premise；
5. closing rule 的 head 已存在时只标记 fired，不覆写 grounded proof；
6. `Ready(Bob)` 不能因为 predicate 相同就支持 `Ready(Alice)`；
7. 无 proof 且覆盖不完整时只能返回 `UNRESOLVED`；
8. not entailed 不等于 contradicted。

## 重新生成

图的单一源文件是 [`generate_visuals.mjs`](./generate_visuals.mjs)。它需要 Node.js、`sharp` 和 `ffmpeg`：

```bash
node generate_visuals.mjs
```

在当前 Codex workspace 中可使用 bundled Node modules，并通过 `FFMPEG_BIN` 指定 ffmpeg：

```bash
NODE_PATH=/Users/chenlong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
FFMPEG_BIN=/opt/homebrew/anaconda3/bin/ffmpeg \
/Users/chenlong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
generate_visuals.mjs
```
