# case_002_debian_12_deepseek-v3_direct_mutex: Debian packages / size 12 / deepseek-v3

- Template: `direct_mutex` (Direct mutual exclusion)
- Root: `libecore-x1` — libecore-x1
- Witness: `libecore-input1` — libecore-input1
- Affected nodes: `libevas1-engines-fb;libevas1`
- SA core nodes: `libecore-evas1;libecore-input1;libevas1;libecore-x1;libevas1-engines-wayland;libevas1-engines-x`
- Naive subgraph nodes: `libecore-input1;libecore-x1;libecore-evas1;libevas1-engines-wayland`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `libecore-x1` | libecore-x1 | mean_score=0.6718749999999998; visit_count=32; conflict_count=34; is_oc_detected=True |
| witness | `libecore-input1` | libecore-input1 | mean_score=0.7914285714285715; visit_count=35; conflict_count=35; is_oc_detected=True |
| affected | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.2333333333333333; visit_count=12; conflict_count=12; is_oc_detected=False |
| affected | `libevas1` | libevas1 | mean_score=0.3386363636363637; visit_count=44; conflict_count=19; is_oc_detected=False |
| sa_core | `libecore-evas1` | libecore-evas1 | mean_score=0.35000000000000003; visit_count=20; conflict_count=2; is_oc_detected=False |
| sa_core | `libecore-input1` | libecore-input1 | mean_score=0.7914285714285715; visit_count=35; conflict_count=35; is_oc_detected=True |
| sa_core | `libevas1` | libevas1 | mean_score=0.3386363636363637; visit_count=44; conflict_count=19; is_oc_detected=False |
| sa_core | `libecore-x1` | libecore-x1 | mean_score=0.6718749999999998; visit_count=32; conflict_count=34; is_oc_detected=True |
| sa_core | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.3896551724137931; visit_count=29; conflict_count=13; is_oc_detected=False |
| sa_core | `libevas1-engines-x` | libevas1-engines-x | mean_score=0.33124999999999993; visit_count=16; conflict_count=8; is_oc_detected=False |
| naive_subgraph | `libecore-input1` | libecore-input1 | mean_score=0.7914285714285715; visit_count=35; conflict_count=35; is_oc_detected=True |
| naive_subgraph | `libecore-x1` | libecore-x1 | mean_score=0.6718749999999998; visit_count=32; conflict_count=34; is_oc_detected=True |
| naive_subgraph | `libecore-evas1` | libecore-evas1 | mean_score=0.35000000000000003; visit_count=20; conflict_count=2; is_oc_detected=False |
| naive_subgraph | `libevas1-engines-wayland` | libevas1-engines-wayland | mean_score=0.3896551724137931; visit_count=29; conflict_count=13; is_oc_detected=False |
| oc | `libecore-input1` | libecore-input1 | mean_score=0.7914285714285715; visit_count=35; conflict_count=35; is_oc_detected=True |
| oc | `libecore-x1` | libecore-x1 | mean_score=0.6718749999999998; visit_count=32; conflict_count=34; is_oc_detected=True |
