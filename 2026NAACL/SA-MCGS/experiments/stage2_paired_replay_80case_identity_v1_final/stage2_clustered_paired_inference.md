# Stage-2 source-SCC 聚类配对区间

状态：80/80 配对 case、20 个 physical source SCC 均通过离线身份与 trace parity 门禁；0 API。

| Metric | Full replacement | Locked no-replacement | Δ Full−Locked | case discordance (+/=/-) |
|---|---:|---:|---:|---:|
| Risk-any | 100.0% [100.0%, 100.0%] | 86.2% [77.5%, 95.0%] | 13.8% [5.0%, 22.5%] | 11/69/0 |
| Risk-all | 75.0% [61.3%, 87.5%] | 37.5% [23.8%, 53.8%] | 37.5% [12.5%, 60.0%] | 41/28/11 |
| Risk coverage | 87.5% [80.6%, 93.8%] | 61.9% [51.9%, 72.5%] | 25.6% [11.2%, 38.8%] | 42/27/11 |

区间为 `20,000` 次 physical-SCC clustered percentile bootstrap（seed=8229）。
同一 SCC 的四个注入 variants 先等权汇总，三位专家或四个 variants 均不作为独立 source SCC。
该区间只描述冻结的 20 个 source SCC，不用于声称真实总体风险率或部署有效性。
