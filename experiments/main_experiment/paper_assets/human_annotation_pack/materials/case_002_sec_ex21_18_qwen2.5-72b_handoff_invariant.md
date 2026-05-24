# case_002_sec_ex21_18_qwen2.5-72b_handoff_invariant: 公司股权/合并披露 / size 18 / qwen2.5-72b

- Template: `handoff_invariant` (前后传递的条件不一致)
- Root: `us-cw-841126` — Entergy Louisiana Holdings LLC
- Witness: `us-cw-118216` — ENTERGY LOUISIANA HOLDINGS INC
- Affected nodes: `us-cw-1001720;us-cw-1280`
- SA core nodes: `us-cw-1180;us-cw-118216;us-cw-1196;us-cw-1280;us-cw-130;us-cw-2080;us-cw-42654;us-cw-59234;us-cw-822`
- Naive subgraph nodes: `us-cw-1180;us-cw-118216;us-cw-1196`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `us-cw-841126` | Entergy Louisiana Holdings LLC | mean_score=0.6599999999999999; visit_count=5; conflict_count=2; is_oc_detected=False |
| witness | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.63; visit_count=10; conflict_count=23; is_oc_detected=True |
| bridge | `us-cw-130` | Entergy Arkansas, Inc | mean_score=0.30000000000000004; visit_count=13; conflict_count=17; is_oc_detected=False |
| affected | `us-cw-1001720` | Entergy International Holdings Ltd | mean_score=0.27142857142857146; visit_count=7; conflict_count=1; is_oc_detected=False |
| affected | `us-cw-1280` | Entergy New Orleans, Inc | mean_score=0.4307692307692308; visit_count=13; conflict_count=19; is_oc_detected=False |
| sa_core | `us-cw-1180` | ENTERGY CORP | mean_score=0.4058823529411765; visit_count=17; conflict_count=28; is_oc_detected=False |
| sa_core | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.63; visit_count=10; conflict_count=23; is_oc_detected=True |
| sa_core | `us-cw-1196` | Entergy Mississippi, Inc | mean_score=0.40322580645161293; visit_count=31; conflict_count=78; is_oc_detected=True |
| sa_core | `us-cw-1280` | Entergy New Orleans, Inc | mean_score=0.4307692307692308; visit_count=13; conflict_count=19; is_oc_detected=False |
| sa_core | `us-cw-130` | Entergy Arkansas, Inc | mean_score=0.30000000000000004; visit_count=13; conflict_count=17; is_oc_detected=False |
| sa_core | `us-cw-2080` | System Energy Resources, Inc | mean_score=0.35517241379310344; visit_count=29; conflict_count=54; is_oc_detected=False |
| sa_core | `us-cw-42654` | Entergy Louisiana LLC | mean_score=0.4; visit_count=30; conflict_count=46; is_oc_detected=False |
| sa_core | `us-cw-59234` | Entergy Texas, Inc | mean_score=0.2727272727272727; visit_count=11; conflict_count=13; is_oc_detected=False |
| sa_core | `us-cw-822` | ENTERGY GULF STATES INC | mean_score=0.42; visit_count=25; conflict_count=40; is_oc_detected=False |
| naive_subgraph | `us-cw-1180` | ENTERGY CORP | mean_score=0.4058823529411765; visit_count=17; conflict_count=28; is_oc_detected=False |
| naive_subgraph | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.63; visit_count=10; conflict_count=23; is_oc_detected=True |
| naive_subgraph | `us-cw-1196` | Entergy Mississippi, Inc | mean_score=0.40322580645161293; visit_count=31; conflict_count=78; is_oc_detected=True |
| oc | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.63; visit_count=10; conflict_count=23; is_oc_detected=True |
| oc | `us-cw-1196` | Entergy Mississippi, Inc | mean_score=0.40322580645161293; visit_count=31; conflict_count=78; is_oc_detected=True |
