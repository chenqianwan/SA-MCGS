# case_007_debian_11_qwen2.5-72b_direct_mutex: Debian packages / size 11 / qwen2.5-72b

- Template: `direct_mutex` (Direct mutual exclusion)
- Root: `node-parse-json` — node-parse-json
- Witness: `node-deep-equal` — node-deep-equal
- Affected nodes: `node-read-pkg;node-debbundle-es-to-primitive`
- SA core nodes: `libjs-util;node-debbundle-es-to-primitive;node-deep-equal;node-es-abstract;node-util`
- Naive subgraph nodes: `node-deep-equal;node-debbundle-es-to-primitive;node-es-abstract;node-tape;node-assert`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `node-parse-json` | node-parse-json | mean_score=0.2076923076923077; visit_count=13; conflict_count=5; is_oc_detected=False |
| witness | `node-deep-equal` | node-deep-equal | mean_score=0.5902439024390244; visit_count=41; conflict_count=59; is_oc_detected=True |
| affected | `node-read-pkg` | node-read-pkg | mean_score=0.09999999999999999; visit_count=11; conflict_count=4; is_oc_detected=False |
| affected | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3033333333333334; visit_count=30; conflict_count=31; is_oc_detected=False |
| sa_core | `libjs-util` | libjs-util | mean_score=0.1444444444444445; visit_count=18; conflict_count=5; is_oc_detected=False |
| sa_core | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3033333333333334; visit_count=30; conflict_count=31; is_oc_detected=False |
| sa_core | `node-deep-equal` | node-deep-equal | mean_score=0.5902439024390244; visit_count=41; conflict_count=59; is_oc_detected=True |
| sa_core | `node-es-abstract` | node-es-abstract | mean_score=0.4818181818181818; visit_count=33; conflict_count=35; is_oc_detected=False |
| sa_core | `node-util` | node-util | mean_score=0.2285714285714286; visit_count=14; conflict_count=7; is_oc_detected=False |
| naive_subgraph | `node-deep-equal` | node-deep-equal | mean_score=0.5902439024390244; visit_count=41; conflict_count=59; is_oc_detected=True |
| naive_subgraph | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3033333333333334; visit_count=30; conflict_count=31; is_oc_detected=False |
| naive_subgraph | `node-es-abstract` | node-es-abstract | mean_score=0.4818181818181818; visit_count=33; conflict_count=35; is_oc_detected=False |
| naive_subgraph | `node-tape` | node-tape | mean_score=0.35833333333333334; visit_count=24; conflict_count=9; is_oc_detected=False |
| naive_subgraph | `node-assert` | node-assert | mean_score=0.13125; visit_count=16; conflict_count=5; is_oc_detected=False |
| oc | `node-deep-equal` | node-deep-equal | mean_score=0.5902439024390244; visit_count=41; conflict_count=59; is_oc_detected=True |
