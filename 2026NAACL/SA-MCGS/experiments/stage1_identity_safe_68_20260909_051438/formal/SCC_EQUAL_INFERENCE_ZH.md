# Stage-1：SCC 等权统计补充

范围为身份错配修复的 17 个 SEC cases，来自 5 个 source SCC；不是全部 80-case 消融。
先在 SCC 内平均 variants，再对 5 个 SCC 等权；按 SCC 配对 bootstrap 20,000 次。
原报告的 case-weighted 点估计和 cluster-bootstrap 保留；二者统计目标不同，不替换原始结果。

| 方法 | Case-level Risk-all | SCC 等权 Risk-all | 相对 Full 差值（95% CI），pp |
|---|---:|---:|---:|
| full-sa-mcgs-rerun | 88.2% | 88.3% | +0.0 [+0.0, +0.0] |
| no-relation-first-memory | 100.0% | 100.0% | +11.7 [+0.0, +25.0] |
| no-critical-pair-ledger-revisit | 100.0% | 100.0% | +11.7 [+0.0, +25.0] |
| random-local-window-selection | 82.4% | 85.0% | -3.3 [-20.0, +15.0] |

所有臂 Root@3、Risk-any 均为 100%。只有 5 个簇，区间仅作探索性描述。
这批结果不支持 relation-first/critical-pair 的正向独立贡献，也不能据此断言其他域没有贡献。
本补充为零 API 离线计算，未改冻结 runner、case 选择或任何结果。
