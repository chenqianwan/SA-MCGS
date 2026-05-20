# case_004_debian_12_deepseek-v3_temporal_gate: Debian packages / size 12 / deepseek-v3

- Template: `temporal_gate` (Temporal gate)
- Root: `libecore-x1` — libecore-x1
- Witness: `libecore-input1` — libecore-input1
- Affected nodes: `libevas1-engines-fb;libevas1`
- SA core nodes: `libecore-evas1;libecore-input1;libevas1;libecore-x1;libevas1-engines-fb;libevas1-engines-wayland`
- Naive subgraph nodes: `libecore-evas1;libevas1-engines-wayland;libevas1`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `libecore-x1` | libecore-x1 | mean_score=0.5411764705882354; visit_count=34; conflict_count=31; is_oc_detected=False |
| witness | `libecore-input1` | libecore-input1 | mean_score=0.513157894736842; visit_count=38; conflict_count=35; is_oc_detected=False |
| affected | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.225; visit_count=8; conflict_count=11; is_oc_detected=False |
| affected | `libevas1` | libevas1 | mean_score=0.3285714285714287; visit_count=28; conflict_count=12; is_oc_detected=False |
| sa_core | `libecore-evas1` | libecore-evas1 | mean_score=0.3631578947368423; visit_count=38; conflict_count=13; is_oc_detected=False |
| sa_core | `libecore-input1` | libecore-input1 | mean_score=0.513157894736842; visit_count=38; conflict_count=35; is_oc_detected=False |
| sa_core | `libevas1` | libevas1 | mean_score=0.3285714285714287; visit_count=28; conflict_count=12; is_oc_detected=False |
| sa_core | `libecore-x1` | libecore-x1 | mean_score=0.5411764705882354; visit_count=34; conflict_count=31; is_oc_detected=False |
| sa_core | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.225; visit_count=8; conflict_count=11; is_oc_detected=False |
| sa_core | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.36538461538461536; visit_count=26; conflict_count=15; is_oc_detected=False |
| naive_subgraph | `libecore-evas1` | libecore-evas1 | mean_score=0.3631578947368423; visit_count=38; conflict_count=13; is_oc_detected=False |
| naive_subgraph | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.36538461538461536; visit_count=26; conflict_count=15; is_oc_detected=False |
| naive_subgraph | `libevas1` | libevas1 | mean_score=0.3285714285714287; visit_count=28; conflict_count=12; is_oc_detected=False |
