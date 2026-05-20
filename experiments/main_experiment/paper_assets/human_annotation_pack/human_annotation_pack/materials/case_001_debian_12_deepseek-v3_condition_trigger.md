# case_001_debian_12_deepseek-v3_condition_trigger: Debian packages / size 12 / deepseek-v3

- Template: `condition_trigger` (Condition trigger)
- Root: `libecore-x1` — libecore-x1
- Witness: `libecore-input1` — libecore-input1
- Affected nodes: `libevas1-engines-fb;libevas1`
- SA core nodes: `libecore-evas1;libecore-input1;libecore-x1;libevas1-engines-fb;libevas1-engines-wayland;libevas1-engines-x`
- Naive subgraph nodes: `libecore-evas1;libevas1;libevas1-engines-wayland;libecore-input1;libecore-drm2-1;libelput1;libevas1-engines-drm`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `libecore-x1` | libecore-x1 | mean_score=0.6517241379310343; visit_count=29; conflict_count=32; is_oc_detected=True |
| witness | `libecore-input1` | libecore-input1 | mean_score=0.4257142857142859; visit_count=35; conflict_count=22; is_oc_detected=False |
| affected | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.20000000000000004; visit_count=12; conflict_count=11; is_oc_detected=False |
| affected | `libevas1` | libevas1 | mean_score=0.30909090909090914; visit_count=22; conflict_count=10; is_oc_detected=False |
| sa_core | `libecore-evas1` | libecore-evas1 | mean_score=0.362962962962963; visit_count=27; conflict_count=5; is_oc_detected=False |
| sa_core | `libecore-input1` | libecore-input1 | mean_score=0.4257142857142859; visit_count=35; conflict_count=22; is_oc_detected=False |
| sa_core | `libecore-x1` | libecore-x1 | mean_score=0.6517241379310343; visit_count=29; conflict_count=32; is_oc_detected=True |
| sa_core | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.20000000000000004; visit_count=12; conflict_count=11; is_oc_detected=False |
| sa_core | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.3518518518518519; visit_count=27; conflict_count=12; is_oc_detected=False |
| sa_core | `libevas1-engines-x` | libevas1-engines-x | mean_score=0.3178571428571428; visit_count=28; conflict_count=18; is_oc_detected=False |
| naive_subgraph | `libecore-evas1` | libecore-evas1 | mean_score=0.362962962962963; visit_count=27; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `libevas1` | libevas1 | mean_score=0.30909090909090914; visit_count=22; conflict_count=10; is_oc_detected=False |
| naive_subgraph | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.3518518518518519; visit_count=27; conflict_count=12; is_oc_detected=False |
| naive_subgraph | `libecore-input1` | libecore-input1 | mean_score=0.4257142857142859; visit_count=35; conflict_count=22; is_oc_detected=False |
| naive_subgraph | `libecore-drm2-1` | libecore-drm2-1 | mean_score=0.18333333333333335; visit_count=12; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `libelput1` | libelput1 | mean_score=0.26666666666666666; visit_count=12; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `libevas1-engines-drm` | libevas1-engines-drm | mean_score=0.23529411764705882; visit_count=17; conflict_count=15; is_oc_detected=False |
| oc | `libecore-x1` | libecore-x1 | mean_score=0.6517241379310343; visit_count=29; conflict_count=32; is_oc_detected=True |
