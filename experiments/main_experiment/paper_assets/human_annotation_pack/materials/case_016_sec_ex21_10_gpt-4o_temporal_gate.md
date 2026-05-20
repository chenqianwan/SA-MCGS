# case_016_sec_ex21_10_gpt-4o_temporal_gate: SEC EX-21 subsidiaries / size 10 / gpt-4o

- Template: `temporal_gate` (Temporal gate)
- Root: `us-cw-515909` — Nielsen Co (Mauritius) Ltd
- Witness: `us-cw-1020294` — TNC (US) Holdings Inc
- Affected nodes: `us-cw-712455;us-cw-749750`
- SA core nodes: `us-cw-1011764;us-cw-1020294;us-cw-749750;us-cw-749751;us-cw-997003`
- Naive subgraph nodes: `us-cw-1020294;us-cw-1011764;us-cw-997003`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.7380952380952384; visit_count=21; conflict_count=23; is_oc_detected=True |
| witness | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.5567567567567566; visit_count=37; conflict_count=65; is_oc_detected=True |
| affected | `us-cw-712455` | PT. The Nielsen Co Indonesia | mean_score=0.4055555555555555; visit_count=18; conflict_count=27; is_oc_detected=False |
| affected | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.21212121212121215; visit_count=33; conflict_count=23; is_oc_detected=False |
| sa_core | `us-cw-1011764` | The Nielsen Company (US) LLC | mean_score=0.303125; visit_count=32; conflict_count=27; is_oc_detected=False |
| sa_core | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.5567567567567566; visit_count=37; conflict_count=65; is_oc_detected=True |
| sa_core | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.21212121212121215; visit_count=33; conflict_count=23; is_oc_detected=False |
| sa_core | `us-cw-749751` | Nielsen Innovate Ltd | mean_score=0.14; visit_count=15; conflict_count=6; is_oc_detected=False |
| sa_core | `us-cw-997003` | Buzzmetrics Ltd | mean_score=0.284375; visit_count=32; conflict_count=20; is_oc_detected=False |
| naive_subgraph | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.5567567567567566; visit_count=37; conflict_count=65; is_oc_detected=True |
| naive_subgraph | `us-cw-1011764` | The Nielsen Company (US) LLC | mean_score=0.303125; visit_count=32; conflict_count=27; is_oc_detected=False |
| naive_subgraph | `us-cw-997003` | Buzzmetrics Ltd | mean_score=0.284375; visit_count=32; conflict_count=20; is_oc_detected=False |
| oc | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.5567567567567566; visit_count=37; conflict_count=65; is_oc_detected=True |
| oc | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.7380952380952384; visit_count=21; conflict_count=23; is_oc_detected=True |
