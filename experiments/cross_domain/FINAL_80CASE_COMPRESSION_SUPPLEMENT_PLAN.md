# Final 80-Case Compression Supplement

最后更新：2026-05-18  
目标：补齐最终论文主实验的 `current/default` 与 `balanced` 两个 compression-profile 结果

---

## 1. 需要补什么

目标：把同一批 `80` 个 critical SCC blocks 在关键模型和两个主压缩口径下补齐：`current/default` 与 `balanced`。

当前缺口：

| 模型组 | Profile | 已有 | 还需要补 | 说明 |
|---|---|---:|---:|---|
| `gpt-4o` + `deepseek-v3` | `current/default` | 80/80 | 0 | 已完成 |
| `gpt-4o` + `deepseek-v3` | `balanced` | 10/80 | 70 | 需要补到 80 |
| `qwen2.5-72b` | `balanced` | 80/80 | 0 | 已完成 |
| `qwen2.5-72b` | `current/default` | 0/80 | 80 | 需要补完整 80 |
| `gemini-2.5-pro` | `current/default` | 0/80 | 80 | 新增强模型补充；带保守 early-stop |
| `gemini-2.5-pro` | `balanced` | 0/80 | 80 | 新增强模型补充；带保守 early-stop |

因此当前最直接需要补：

```text
DS/GPT balanced:          70 blocks
Qwen current:             80 blocks
Gemini 2.5 Pro current:   80 blocks
Gemini 2.5 Pro balanced:  80 blocks
Total:                   310 blocks
```

对照说明：

- `critical_paper_v3_b60`
  - models: `gpt-4o`, `deepseek-v3`
  - cases: 80
  - compression profile: `current/default`
- `compression_profile_sweep_b60_net`
  - models: `gpt-4o`, `deepseek-v3`
  - `conservative / balanced / aggressive` 各已有 10 个 blocks
  - 最终主实验只取 `balanced` 这一路；`conservative/aggressive` 作为调参诊断，不进入主补齐目标
- `critical_balanced_b60_supp_qwen_gemini`
  - models: `qwen2.5-72b`, `gemini-2.5-flash`
  - balanced 80 blocks
  - 其中 Qwen balanced 可作为补充模型 balanced 结果

暂不优先补：

- DS/GPT `conservative/aggressive` 全 80：这是 profile sweep 诊断，不进入当前主补齐目标。
- Qwen `conservative`：同样不进入当前主补齐目标。
- Gemini Flash：当前 SA-MCGS 表现异常，不进入主补齐目标。
- Gemini 2.5 Pro：`current/default` 和 `balanced` 都需要补，但必须先做小样本健康检查。

Naive 如果因为输入太长、JSON 解析、API 返回等失败，主统计中仍然计入分母，并算作失败。

---

## 2. 总数据集

总共 80 个 critical SCC blocks：

| Domain | SCC sizes | Blocks |
|---|---|---:|
| Debian | 11, 12 | 8 |
| SEC EX-21 | 9, 10, 11, 12, 18 | 20 |
| BGB | 9, 11, 25 | 12 |
| CUAD | 12, 14, 16, 17, 18, 20, 24, 25, 28, 34 | 40 |
| **Total** | - | **80** |

每个 size 跑 4 个注入模板：

- `direct_mutex`
- `handoff_invariant`
- `temporal_gate`
- `condition_trigger`

全部使用：

- `memory_stress`
- `structural_simple_v2`
- `critical`
- real SCC
- SA-MCGS rollout budget = 60

---

## 3. 任务规模

当前需要补的 block 数：

```text
70 + 80 + 80 + 80 = 310 blocks
```

如果每个 block 都跑 Naive + SA-MCGS：

```text
310 × 2 methods = 620 method-level records
```

如果 compression 补齐只跑 SA-MCGS，并复用已有 Naive：

```text
310 × 1 method = 310 method-level records
```

建议：

- DS/GPT balanced：优先只补 `sa-mcgs`，Naive 复用同一批 case 的 `current/default` Naive；如果最终审稿口径要求 profile 内完全成对，再补 Naive。
- Qwen current：跑 `naive + sa-mcgs`，因为这是新的 profile baseline。
- Gemini 2.5 Pro current/balanced：先跑 `naive + sa-mcgs` 小样本健康检查，通过后再补完整 80。

---

## 4. 运行命令草案

### 4.1 DS/GPT balanced 补到 80

补缺口：`70 blocks`

建议 run tag：

```text
critical_dsgpt_balanced_fill80_b60
```

### 4.2 Qwen current 补 80

补缺口：`80 blocks`

建议 run tag：

```text
critical_qwen_current_full80_b60
```

### 4.3 Gemini 2.5 Pro current 补 80

补缺口：`80 blocks`

建议 run tag：

```text
critical_gemini25pro_current_full80_b60
```

### 4.4 Gemini 2.5 Pro balanced 补 80

补缺口：`80 blocks`

建议 run tag：

```text
critical_gemini25pro_balanced_full80_b60
```

先跑健康检查，再决定是否继续：

- 先跑 `8-12` 个 blocks，覆盖至少 `2` 个 domain、`2` 个 template。
- 只有在 SA-MCGS 明显复现 Flash 异常时才停：例如 valid SA 输出里 `Root@3=0`、`Risk-any` 接近 0、`Risk-all=0`、`Effective OC=0`，并且 core 反复退化成单节点或无效节点。
- 如果只是少数 hard case 失败，不停止；继续完整 80。
- 如果是 API/JSON/额度错误，不把它解释成模型能力失败，先暂停并保留已成功结果。

---

## 5. 最终要看的指标

主表：

- `Root@3`
- `Risk-any`
- `Risk-all`
- `Compression`
- `Effective OC`
- `Error rate`

最终比较：

```text
DS/GPT: current/default vs balanced
Qwen:   current/default vs balanced
Gemini 2.5 Pro: current/default vs balanced, only if health check passes
```

目标：确认 `balanced` 是否能在不明显损害 Root@3 / Risk-any / Risk-all 的情况下，提高 compression。
