# 三波聚合口径

每波运行80例×3模型×2基线，共480组，三波共1440组新结果。旧SA固定复用原240组，只列一次，不伪造重复标准差。

wave1为`equal_budget_all80_20261009`，后续为`equal_budget_all80_wave2_20261010`和`equal_budget_all80_wave3_20261010`。早先10例pilot不计入。三波设置相同，Python及评选seed保持42，未显式传服务端seed；这是相同设置下三次新采样，不称不同随机种子的实验。

Risk-all、Root@3、Risk-any每波固定除以80，严格失败计0。三波完整后，对三个波次比率等权计算均值和样本标准差（ddof=1）。

压缩率逐例为1−|H|/|SCC|，先在每波有效输出中取算术平均，再对三个波均值等权计算均值和样本标准差，同时报告各波有效例数。失败压缩率为null，不能当作100%；任何一波无有效例时，三波压缩率统计保持未定义。

任意波次未齐480个终态，或存在未结算用量、预算不一致，正式三波均值和标准差均保持null。逐波进度、严格失败和基础设施失败全部保留，不跳过波次。重复波动不是独立测试样本的置信区间。

脚本只读取各波原始文件，在父目录输出`aggregate_summary.json`及`AGGREGATE_ZH.md`。JSON保留每个final的指标、用量、状态、路径与SHA256。

中文总表按模型将固定SA和LEA、Full-SCC三波结果放在一起，四列为Risk-all、Root@3、Risk-any和压缩率。SA标准差显示“—”；三波完整后每模型每列最高数值加粗，并列均加粗，比较未舍入值。未完整时基线显示待完成，不标最优。

父目录`manifest.json`需包含恰好三个`wave_dirs`（字符串列表，或带`wave_id`和`path`的对象列表）；相对目录按`experiments`根解析。可选`historical_sa_reference`指定固定旧SA引用，缺省用wave1目录中的同名文件。运行：

```sh
python3 aggregate_three_waves.py --manifest manifest.json
```

在其他工作目录调用时，将脚本及manifest写成绝对路径；也可用`--experiments-root`和`--output-dir`显式指定位置。
