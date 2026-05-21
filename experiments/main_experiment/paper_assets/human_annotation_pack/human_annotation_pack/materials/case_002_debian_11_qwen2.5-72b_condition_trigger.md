# case_002_debian_11_qwen2.5-72b_condition_trigger: Debian packages / size 11 / qwen2.5-72b

- Template: `condition_trigger` (Condition trigger)
- Root: `node-parse-json` — node-parse-json
- Witness: `node-deep-equal` — node-deep-equal
- Affected nodes: `node-read-pkg;node-debbundle-es-to-primitive`
- SA core nodes: `libjs-util;node-debbundle-es-to-primitive;node-deep-equal;node-es-abstract;node-util`
- Naive subgraph nodes: `node-deep-equal;node-debbundle-es-to-primitive;node-es-abstract;node-tape`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `node-parse-json` | node-parse-json | mean_score=0.2818181818181818; visit_count=11; conflict_count=7; is_oc_detected=False |
| witness | `node-deep-equal` | node-deep-equal | mean_score=0.4666666666666667; visit_count=42; conflict_count=48; is_oc_detected=False |
| affected | `node-read-pkg` | node-read-pkg | mean_score=0.0923076923076923; visit_count=13; conflict_count=5; is_oc_detected=False |
| affected | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3333333333333333; visit_count=33; conflict_count=20; is_oc_detected=False |
| sa_core | `libjs-util` | libjs-util | mean_score=0.2866666666666667; visit_count=15; conflict_count=8; is_oc_detected=False |
| sa_core | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3333333333333333; visit_count=33; conflict_count=20; is_oc_detected=False |
| sa_core | `node-deep-equal` | node-deep-equal | mean_score=0.4666666666666667; visit_count=42; conflict_count=48; is_oc_detected=False |
| sa_core | `node-es-abstract` | node-es-abstract | mean_score=0.5078947368421053; visit_count=38; conflict_count=33; is_oc_detected=True |
| sa_core | `node-util` | node-util | mean_score=0.2642857142857143; visit_count=14; conflict_count=7; is_oc_detected=False |
| naive_subgraph | `node-deep-equal` | node-deep-equal | mean_score=0.4666666666666667; visit_count=42; conflict_count=48; is_oc_detected=False |
| naive_subgraph | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.3333333333333333; visit_count=33; conflict_count=20; is_oc_detected=False |
| naive_subgraph | `node-es-abstract` | node-es-abstract | mean_score=0.5078947368421053; visit_count=38; conflict_count=33; is_oc_detected=True |
| naive_subgraph | `node-tape` | node-tape | mean_score=0.28076923076923077; visit_count=26; conflict_count=4; is_oc_detected=False |
| oc | `node-es-abstract` | node-es-abstract | mean_score=0.5078947368421053; visit_count=38; conflict_count=33; is_oc_detected=True |
