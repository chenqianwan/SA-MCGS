# E3. Compression Profile Ablation

目的：把 `current/default` 主实验和 `balanced` 压缩强度分开。主论文只用 current/default；balanced 只作为压缩率-召回率 trade-off 补充。

| Profile | Method | N | Unavailable outputs | Root@3 | Risk-any | Risk-all | Compression | Effective Compression | Avg Subgraph |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current/default | naive | 320 | 59 | 48% | 72% | 47% | 67% | 66% | 4.44 |
| current/default | sa-mcgs | 320 | 0 | 81% | 98% | 78% | 53% | 53% | 7.69 |
| balanced | naive | 160 | 44 | 48% | 72% | 51% | 65% | 65% | 4.46 |
| balanced | sa-mcgs | 320 | 0 | 80% | 97% | 71% | 63% | 63% | 5.91 |
