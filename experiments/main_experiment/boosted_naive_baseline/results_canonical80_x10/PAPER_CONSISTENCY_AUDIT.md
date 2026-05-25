# Paper 口径与备注审查报告

审查对象：

- [`paper/latex/acl_latex.tex`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex)
- 重点检查：oracle-risk baseline 口径、one-shot / boosted / SA-MCGS 分母与叙述、figure/table caption、是否混入类似助手备注的文字。

结论先说：

- 没有发现 `should not`、`需要确认`、`建议改后`、`AI/assistant/Codex` 这类给用户看的备注进入 LaTeX 正文。
- 仍有几处口径和论文写法需要修，尤其是 conclusion/limitations 里仍有一点旧 baseline 语气。

## 1. 必须修的口径问题

### 1.1 `paper-facing` 是内部用语，不建议出现在 paper

位置：

- [`acl_latex.tex:310`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:310)
- [`acl_latex.tex:711`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:711)
- [`acl_latex.tex:789`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:789)

状态：

已修。LaTeX 中的 `paper-facing comparison` / `paper-facing baseline` 已改为 `main comparison` / `main baseline`。

建议统一改成：

- `main comparison`
- `main baseline`
- `reported baseline`

建议替换：

改前：
The paper-facing comparison contains 320 model-case pairs per method; oracle-risk Naive is selected from 3,200 raw full-SCC attempts.

改后：
The main comparison contains 320 model-case pairs per method; oracle-risk Naive is selected from 3,200 raw full-SCC attempts.

改前：
the paper-facing baseline aggregates ten such attempts with oracle-risk Top-3 selection

改后：
the main baseline aggregates ten such attempts with oracle-risk Top-3 selection

改前：
The paper-facing Naive baseline is oracle-risk Top-3 selection over ten full-SCC direct-subgraph attempts per model-case.

改后：
The main Naive baseline is oracle-risk Top-3 selection over ten full-SCC direct-subgraph attempts per model-case.

### 1.2 Selector table caption 里 `diagnostic` 和 `main baseline` 有冲突

位置：

- [`acl_latex.tex:819`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:819)
- [`acl_latex.tex:824`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:824)

状态：

已修。`boosted Naive oracle-risk Top-3` 的 role 已改为 `main oracle-risk baseline`，caption 已改为说明 oracle selectors 使用 ground-truth metrics for selection，同时明确 self Top-3 是 non-oracle boosted selector。

已采用改法：

Oracle selectors use ground-truth evaluation metrics for selection; oracle-risk Top-3 is the main oracle-risk baseline, while self Top-3 is the non-oracle boosted selector.

main oracle-risk baseline

### 1.3 Conclusion 仍然像旧 baseline 口径

位置：

- [`acl_latex.tex:373`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:373)

状态：

已修。Conclusion 已明确使用 oracle-risk Top-3 repeated full-SCC baseline 口径。

当前句子：

Across four domains and four LLMs, this yields stronger root localization and endpoint retention than an oracle-risk Top-3 baseline built from repeated full-SCC direct-subgraph attempts. It also makes the cost in compression explicit.

### 1.4 Token budget comparable 这句需要证据或弱化

位置：

- [`acl_latex.tex:310`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:310)

当前句子：

This gives boosted Naive a total token budget comparable to SA-MCGS.

问题：

这句是合理方向，但目前正文和附录没有给出 SA-MCGS 的 token 总量或 token audit 表。Boosted Naive report 里有 raw observed tokens，但我没有在当前 `sa-mcgs` result records 里看到同级别 token 字段。因此如果保留 “comparable”，最好补一个来源或把语气弱化。

建议二选一：

方案 A，补证据：

Add an appendix token-budget note/table with boosted Naive total tokens and SA-MCGS total tokens.

方案 B，正文弱化：

改前：
This gives boosted Naive a total token budget comparable to SA-MCGS.

改后：
This makes boosted Naive a stronger budgeted full-SCC baseline than a one-shot prompt.

或者：

This makes the baseline closer to the SA-MCGS budget than a one-shot full-SCC prompt.

## 2. 建议统一的命名问题

### 2.1 `oracle-risk` 命名统一已修

当前出现位置：

- Abstract: `oracle-risk Top-3`
- Contribution: `oracle-risk full-SCC direct-subgraph baseline`
- Baseline definition: `oracle-risk Naive` and `risk-prioritized oracle`
- Figure caption: `oracle-risk Naive`, `oracle-risk Top-3`
- Appendix: `oracle-risk Top-3`

此前问题：

含义基本一致，但术语太多。建议只保留两层：

- 方法名：`oracle-risk Naive`
- 机制解释：`risk-prioritized oracle`

当前口径：

已把泛称里的相关表述统一成 `oracle-risk`，并只保留 `risk-prioritized oracle` 用于解释选择机制。正文/图注现在使用：

- `an oracle-risk full-SCC direct-subgraph baseline`
- `an oracle-risk Top-3 selection over ten full-SCC attempts`

### 2.2 Selector role 内部用语已修

位置：

- [`acl_latex.tex:819`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:819)

状态：已修为 `main oracle-risk baseline`。

### 2.3 `paper-facing comparison` 和 `paper-facing baseline` 应统一替换

状态：已修。LaTeX 中不再出现 `paper-facing`。

## 3. 可能需要澄清但不是硬错误

### 3.1 Limitations 仍然说 SA-MCGS 比 one-shot prompting 更贵

位置：

- [`acl_latex.tex:378`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:378)

当前句子：

SA-MCGS incurs higher cost than one-shot prompting due to its local LLM calls.

判断：

这句话单独看是对的，因为 one-shot Naive 仍然是附录 control。但主 baseline 已经换成 boosted oracle-risk Naive，并且正文刚说 boosted Naive token budget comparable to SA-MCGS，所以这里容易被读者理解成旧主 baseline。

建议改成更精确：

SA-MCGS incurs higher cost than a single full-SCC prompt due to its local LLM calls.

如果保留 token comparable 句，也可以补一句：

The oracle-risk boosted baseline controls for this by repeated full-SCC attempts, but ordinary one-shot prompting remains cheaper.

### 3.2 Robustness paragraph 没有直接点出 oracle-risk 主 baseline

位置：

- [`acl_latex.tex:352`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:352)

当前：

The non-oracle boosted selector reaches 52% Risk-all, while compression-first oracle selection raises compression but lowers Risk-all to 47%.

判断：

这句话没错，但读者可能会想：那主 oracle-risk selector 是多少？前文已经讲过主结果，所以不是硬问题。

可选改法：

Appendix reports selector and reliability checks around the oracle-risk main baseline.

### 3.3 `Qwen2.5-72B-Instruct` vs `Qwen2.5-72B`

位置：

- [`acl_latex.tex:310`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:310)
- [`acl_latex.tex:878`](/Users/chenlong/.codex/worktrees/fecd/MCGS_Law/paper/latex/acl_latex.tex:878)

判断：

正文写 `Qwen2.5-72B-Instruct`，表里写 `Qwen2.5-72B`。不是严重口径问题，但为了一致性可以统一成一个显示名。

## 4. 已检查但没发现问题的点

### 4.1 没发现助手备注进入 LaTeX

扫描关键词包括：

- `should not`
- `need confirm`
- `确认`
- `建议`
- `建议改后`
- `需要你`
- `default paper`
- `deliberately strong`
- `assistant`
- `ChatGPT`
- `Codex`
- `警告`
- `备注`

结果：

- `paper/latex/acl_latex.tex` 没有这些助手备注类命中。
- `.bbl/.bib` 里的 `AI` 只来自正常会议/期刊名，例如 AAAI / IJCAI，不是助手备注。

### 4.2 主结果数字基本对齐

正文主结果：

- Root@3: 58% -> 81%
- Risk-any: 79% -> 98%
- Risk-all: 62% -> 78%
- Gains: +23 / +19 / +16

与 Figure 3 / main table 口径一致。

### 4.3 Reliability 分母基本清楚

当前附录 reliability table 同时列：

- one-shot Naive model-cases: 261/320 usable
- SA-MCGS model-cases: 320/320 usable
- boosted Naive raw attempts: 2400/3200 usable
- boosted Naive model-cases: 274/320 usable

口径上是清楚的。主要需要注意的是不要把 raw-attempt 的 `800/3200` 和 model-case 的 `46/320` 混到正文主表里。目前主表没有混。

### 4.4 错误原因口径基本对齐

当前 paper 将 boosted/Naive 失败解释为：

- long-context pressure
- output-schema burden
- timeout
- unparseable through incomplete, duplicate, or invalid rankings

没有写成 quota failure、network error、provider instability 之类不稳的原因。

## 5. 推荐下一步最小修改清单

按优先级：

1. `oracle-risk` 命名已统一，保留 `oracle-risk Naive` 作为方法名。
2. 处理 token budget comparable 句：补 SA-MCGS token evidence，或把语气弱化。
3. Limitations 把 `one-shot prompting` 改成 `a single full-SCC prompt`，避免读者以为还在讲旧主 baseline。
