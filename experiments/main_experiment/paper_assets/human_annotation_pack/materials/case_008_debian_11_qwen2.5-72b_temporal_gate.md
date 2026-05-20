# case_008_debian_11_qwen2.5-72b_temporal_gate: Debian packages / size 11 / qwen2.5-72b

- Template: `temporal_gate` (Temporal gate)
- Root: `node-parse-json` — node-parse-json
- Witness: `node-deep-equal` — node-deep-equal
- Affected nodes: `node-read-pkg;node-debbundle-es-to-primitive`
- SA core nodes: `node-debbundle-es-to-primitive;node-deep-equal;node-es-abstract;node-istanbul;node-tape`
- Naive subgraph nodes: `node-deep-equal;node-debbundle-es-to-primitive;node-es-abstract`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `node-parse-json` | node-parse-json | mean_score=0.20555555555555555; visit_count=18; conflict_count=3; is_oc_detected=False |
| witness | `node-deep-equal` | node-deep-equal | mean_score=0.3108108108108108; visit_count=37; conflict_count=44; is_oc_detected=False |
| affected | `node-read-pkg` | node-read-pkg | mean_score=0.16666666666666674; visit_count=21; conflict_count=4; is_oc_detected=False |
| affected | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.18076923076923077; visit_count=26; conflict_count=12; is_oc_detected=False |
| sa_core | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.18076923076923077; visit_count=26; conflict_count=12; is_oc_detected=False |
| sa_core | `node-deep-equal` | node-deep-equal | mean_score=0.3108108108108108; visit_count=37; conflict_count=44; is_oc_detected=False |
| sa_core | `node-es-abstract` | node-es-abstract | mean_score=0.3258064516129032; visit_count=31; conflict_count=30; is_oc_detected=True |
| sa_core | `node-istanbul` | node-istanbul | mean_score=0.1956521739130435; visit_count=23; conflict_count=15; is_oc_detected=False |
| sa_core | `node-tape` | node-tape | mean_score=0.22749999999999998; visit_count=40; conflict_count=19; is_oc_detected=False |
| naive_subgraph | `node-deep-equal` | node-deep-equal | mean_score=0.3108108108108108; visit_count=37; conflict_count=44; is_oc_detected=False |
| naive_subgraph | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.18076923076923077; visit_count=26; conflict_count=12; is_oc_detected=False |
| naive_subgraph | `node-es-abstract` | node-es-abstract | mean_score=0.3258064516129032; visit_count=31; conflict_count=30; is_oc_detected=True |
| oc | `node-es-abstract` | node-es-abstract | mean_score=0.3258064516129032; visit_count=31; conflict_count=30; is_oc_detected=True |
