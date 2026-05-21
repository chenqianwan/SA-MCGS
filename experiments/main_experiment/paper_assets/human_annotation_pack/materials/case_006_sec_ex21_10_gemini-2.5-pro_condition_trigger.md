# case_006_sec_ex21_10_gemini-2.5-pro_condition_trigger: SEC EX-21 subsidiaries / size 10 / gemini-2.5-pro

- Template: `condition_trigger` (Condition trigger)
- Root: `us-cw-515909` — Nielsen Co (Mauritius) Ltd
- Witness: `us-cw-1020294` — TNC (US) Holdings Inc
- Affected nodes: `us-cw-712455;us-cw-749750`
- SA core nodes: `us-cw-1011764;us-cw-1020294;us-cw-749750;us-cw-749751;us-cw-997003`
- Naive subgraph nodes: `us-cw-515909;us-cw-712455;us-cw-515912;us-cw-997003;us-cw-1020294`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.5812500000000002; visit_count=16; conflict_count=4; is_oc_detected=False |
| witness | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9948717948717948; visit_count=39; conflict_count=36; is_oc_detected=True |
| affected | `us-cw-712455` | PT. The Nielsen Co Indonesia | mean_score=0.32142857142857145; visit_count=14; conflict_count=2; is_oc_detected=False |
| affected | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.39714285714285713; visit_count=35; conflict_count=11; is_oc_detected=False |
| sa_core | `us-cw-1011764` | The Nielsen Company (US) LLC | mean_score=0.7812499999999999; visit_count=32; conflict_count=28; is_oc_detected=True |
| sa_core | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9948717948717948; visit_count=39; conflict_count=36; is_oc_detected=True |
| sa_core | `us-cw-749750` | Nielsen Innovate Fund LP | mean_score=0.39714285714285713; visit_count=35; conflict_count=11; is_oc_detected=False |
| sa_core | `us-cw-749751` | Nielsen Innovate Ltd | mean_score=0.3782608695652174; visit_count=23; conflict_count=5; is_oc_detected=False |
| sa_core | `us-cw-997003` | Buzzmetrics Ltd | mean_score=0.28518518518518515; visit_count=27; conflict_count=0; is_oc_detected=False |
| naive_subgraph | `us-cw-515909` | Nielsen Co (Mauritius) Ltd | mean_score=0.5812500000000002; visit_count=16; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `us-cw-712455` | PT. The Nielsen Co Indonesia | mean_score=0.32142857142857145; visit_count=14; conflict_count=2; is_oc_detected=False |
| naive_subgraph | `us-cw-515912` | Nielsen Co (Singapore) Pte. Ltd | mean_score=0.4263157894736842; visit_count=19; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `us-cw-997003` | Buzzmetrics Ltd | mean_score=0.28518518518518515; visit_count=27; conflict_count=0; is_oc_detected=False |
| naive_subgraph | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9948717948717948; visit_count=39; conflict_count=36; is_oc_detected=True |
| oc | `us-cw-1011764` | The Nielsen Company (US) LLC | mean_score=0.7812499999999999; visit_count=32; conflict_count=28; is_oc_detected=True |
| oc | `us-cw-1020294` | TNC (US) Holdings Inc | mean_score=0.9948717948717948; visit_count=39; conflict_count=36; is_oc_detected=True |
