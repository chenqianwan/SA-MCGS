# case_003_debian_12_deepseek-v3_handoff_invariant: Debian packages / size 12 / deepseek-v3

- Template: `handoff_invariant` (Handoff invariant)
- Root: `libecore-x1` — libecore-x1
- Witness: `libecore-input1` — libecore-input1
- Affected nodes: `libevas1-engines-fb;libevas1`
- SA core nodes: `libecore-input1;libevas1;libevas1-engines-drm;libecore-x1;libevas1-engines-fb;libevas1-engines-x`
- Naive subgraph nodes: `libecore-x1;libecore-input1;libecore-evas1`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `libecore-x1` | libecore-x1 | mean_score=0.7428571428571431; visit_count=28; conflict_count=25; is_oc_detected=True |
| witness | `libecore-input1` | libecore-input1 | mean_score=0.5512195121951218; visit_count=41; conflict_count=38; is_oc_detected=True |
| affected | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.21000000000000002; visit_count=10; conflict_count=10; is_oc_detected=False |
| affected | `libevas1` | libevas1 | mean_score=0.3333333333333335; visit_count=36; conflict_count=27; is_oc_detected=False |
| sa_core | `libecore-input1` | libecore-input1 | mean_score=0.5512195121951218; visit_count=41; conflict_count=38; is_oc_detected=True |
| sa_core | `libevas1` | libevas1 | mean_score=0.3333333333333335; visit_count=36; conflict_count=27; is_oc_detected=False |
| sa_core | `libevas1-engines-drm` | libevas1-engines-drm | mean_score=0.21875000000000006; visit_count=16; conflict_count=14; is_oc_detected=False |
| sa_core | `libecore-x1` | libecore-x1 | mean_score=0.7428571428571431; visit_count=28; conflict_count=25; is_oc_detected=True |
| sa_core | `libevas1-engines-fb` | libevas1-engines-fb | mean_score=0.21000000000000002; visit_count=10; conflict_count=10; is_oc_detected=False |
| sa_core | `libevas1-engines-x` | libevas1-engines-x | mean_score=0.25263157894736843; visit_count=19; conflict_count=15; is_oc_detected=False |
| naive_subgraph | `libecore-x1` | libecore-x1 | mean_score=0.7428571428571431; visit_count=28; conflict_count=25; is_oc_detected=True |
| naive_subgraph | `libecore-input1` | libecore-input1 | mean_score=0.5512195121951218; visit_count=41; conflict_count=38; is_oc_detected=True |
| naive_subgraph | `libecore-evas1` | libecore-evas1 | mean_score=0.30869565217391304; visit_count=23; conflict_count=6; is_oc_detected=False |
| oc | `libecore-input1` | libecore-input1 | mean_score=0.5512195121951218; visit_count=41; conflict_count=38; is_oc_detected=True |
| oc | `libecore-x1` | libecore-x1 | mean_score=0.7428571428571431; visit_count=28; conflict_count=25; is_oc_detected=True |
