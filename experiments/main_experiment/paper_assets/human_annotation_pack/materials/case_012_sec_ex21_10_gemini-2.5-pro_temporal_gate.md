# case_012_sec_ex21_10_gemini-2.5-pro_temporal_gate: SEC EX-21 subsidiaries / size 10 / gemini-2.5-pro

- Template: `temporal_gate` (Temporal gate)
- Root: `us-cw-515909` — Nielsen Co (Mauritius) Ltd
- Witness: `us-cw-1020294` — TNC (US) Holdings Inc
- Affected nodes: `us-cw-712455;us-cw-749750`
- SA core nodes: `us-cw-1011764;us-cw-1020294;us-cw-121873;us-cw-749749;us-cw-749750`
- Naive subgraph nodes: `us-cw-515909;us-cw-712455;us-cw-515912;us-cw-997003;us-cw-1020294`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.6166666666666667; visit_count=18; conflict_count=6; is_oc_detected=False |
| witness | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9512820512820508; visit_count=39; conflict_count=44; is_oc_detected=True |
| affected | `us-cw-712455` | PT. The Nielsen Co Indonesia | mean_score=0.2692307692307692; visit_count=13; conflict_count=3; is_oc_detected=False |
| affected | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.4594594594594594; visit_count=37; conflict_count=14; is_oc_detected=False |
| sa_core | `us-cw-1011764` | The Nielsen Company (US) LLC | mean_score=0.7111111111111111; visit_count=36; conflict_count=27; is_oc_detected=False |
| sa_core | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9512820512820508; visit_count=39; conflict_count=44; is_oc_detected=True |
| sa_core | `us-cw-121873` | NetRatings Australia Pty. Ltd | mean_score=0.3; visit_count=18; conflict_count=5; is_oc_detected=False |
| sa_core | `us-cw-749749` | Nielsen Co Ltd | mean_score=0.39166666666666666; visit_count=12; conflict_count=5; is_oc_detected=False |
| sa_core | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.4594594594594594; visit_count=37; conflict_count=14; is_oc_detected=False |
| naive_subgraph | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.6166666666666667; visit_count=18; conflict_count=6; is_oc_detected=False |
| naive_subgraph | `us-cw-712455` | PT. The Nielsen Co Indonesia | mean_score=0.2692307692307692; visit_count=13; conflict_count=3; is_oc_detected=False |
| naive_subgraph | `us-cw-515912` | Nielsen Co (Singapore) Pte. Ltd | mean_score=0.40625; visit_count=16; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `us-cw-997003` | Buzzmetrics Ltd | mean_score=0.30571428571428566; visit_count=35; conflict_count=1; is_oc_detected=False |
| naive_subgraph | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9512820512820508; visit_count=39; conflict_count=44; is_oc_detected=True |
| oc | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9512820512820508; visit_count=39; conflict_count=44; is_oc_detected=True |
