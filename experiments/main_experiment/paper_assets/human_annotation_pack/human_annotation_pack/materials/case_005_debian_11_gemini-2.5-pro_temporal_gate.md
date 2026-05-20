# case_005_debian_11_gemini-2.5-pro_temporal_gate: Debian packages / size 11 / gemini-2.5-pro

- Template: `temporal_gate` (Temporal gate)
- Root: `node-parse-json` — node-parse-json
- Witness: `node-deep-equal` — node-deep-equal
- Affected nodes: `node-read-pkg;node-debbundle-es-to-primitive`
- SA core nodes: `node-deep-equal;node-es-abstract;node-istanbul;node-read-pkg;node-tape`
- Naive subgraph nodes: `node-deep-equal;node-tape;node-parse-json;node-es-abstract;node-debbundle-es-to-primitive;node-istanbul;node-read-pkg`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `node-parse-json` | node-parse-json | mean_score=0.4950000000000001; visit_count=20; conflict_count=8; is_oc_detected=False |
| witness | `node-deep-equal` | node-deep-equal | mean_score=0.7944444444444445; visit_count=36; conflict_count=32; is_oc_detected=True |
| affected | `node-read-pkg` | node-read-pkg | mean_score=0.4428571428571429; visit_count=21; conflict_count=8; is_oc_detected=False |
| affected | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.2692307692307692; visit_count=13; conflict_count=0; is_oc_detected=False |
| sa_core | `node-deep-equal` | node-deep-equal | mean_score=0.7944444444444445; visit_count=36; conflict_count=32; is_oc_detected=True |
| sa_core | `node-es-abstract` | node-es-abstract | mean_score=0.6129032258064516; visit_count=31; conflict_count=14; is_oc_detected=True |
| sa_core | `node-istanbul` | node-istanbul | mean_score=0.3846153846153845; visit_count=26; conflict_count=5; is_oc_detected=False |
| sa_core | `node-read-pkg` | node-read-pkg | mean_score=0.4428571428571429; visit_count=21; conflict_count=8; is_oc_detected=False |
| sa_core | `node-tape` | node-tape | mean_score=0.6473684210526315; visit_count=38; conflict_count=19; is_oc_detected=False |
| naive_subgraph | `node-deep-equal` | node-deep-equal | mean_score=0.7944444444444445; visit_count=36; conflict_count=32; is_oc_detected=True |
| naive_subgraph | `node-tape` | node-tape | mean_score=0.6473684210526315; visit_count=38; conflict_count=19; is_oc_detected=False |
| naive_subgraph | `node-parse-json` | node-parse-json | mean_score=0.4950000000000001; visit_count=20; conflict_count=8; is_oc_detected=False |
| naive_subgraph | `node-es-abstract` | node-es-abstract | mean_score=0.6129032258064516; visit_count=31; conflict_count=14; is_oc_detected=True |
| naive_subgraph | `node-debbundle-es-to-primitive` | node-debbundle-es-to-primitive | mean_score=0.2692307692307692; visit_count=13; conflict_count=0; is_oc_detected=False |
| naive_subgraph | `node-istanbul` | node-istanbul | mean_score=0.3846153846153845; visit_count=26; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `node-read-pkg` | node-read-pkg | mean_score=0.4428571428571429; visit_count=21; conflict_count=8; is_oc_detected=False |
| oc | `node-deep-equal` | node-deep-equal | mean_score=0.7944444444444445; visit_count=36; conflict_count=32; is_oc_detected=True |
| oc | `node-es-abstract` | node-es-abstract | mean_score=0.6129032258064516; visit_count=31; conflict_count=14; is_oc_detected=True |
