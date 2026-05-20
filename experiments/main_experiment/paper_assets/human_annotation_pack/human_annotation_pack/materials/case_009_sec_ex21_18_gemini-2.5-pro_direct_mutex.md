# case_009_sec_ex21_18_gemini-2.5-pro_direct_mutex: SEC EX-21 subsidiaries / size 18 / gemini-2.5-pro

- Template: `direct_mutex` (Direct mutual exclusion)
- Root: `us-cw-841126` — Entergy Louisiana Holdings LLC
- Witness: `us-cw-118216` — ENTERGY LOUISIANA HOLDINGS INC
- Affected nodes: `us-cw-1001720;us-cw-1280`
- SA core nodes: `us-cw-1180;us-cw-118216;us-cw-1196;us-cw-1280;us-cw-130;us-cw-2080;us-cw-3379182;us-cw-822`
- Naive subgraph nodes: `us-cw-118216;us-cw-841126;us-cw-42654;us-cw-1180`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `us-cw-841126` | Entergy Louisiana Holdings LLC | mean_score=0.36; visit_count=5; conflict_count=0; is_oc_detected=False |
| witness | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.9464285714285712; visit_count=28; conflict_count=31; is_oc_detected=True |
| affected | `us-cw-1001720` | Entergy International Holdings Ltd | mean_score=0.14999999999999997; visit_count=10; conflict_count=1; is_oc_detected=False |
| affected | `us-cw-1280` | Entergy New Orleans, Inc | mean_score=0.5083333333333334; visit_count=24; conflict_count=16; is_oc_detected=False |
| sa_core | `us-cw-1180` | ENTERGY CORP | mean_score=0.6448275862068966; visit_count=29; conflict_count=37; is_oc_detected=False |
| sa_core | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.9464285714285712; visit_count=28; conflict_count=31; is_oc_detected=True |
| sa_core | `us-cw-1196` | Entergy Mississippi, Inc | mean_score=0.4375; visit_count=16; conflict_count=6; is_oc_detected=False |
| sa_core | `us-cw-1280` | Entergy New Orleans, Inc | mean_score=0.5083333333333334; visit_count=24; conflict_count=16; is_oc_detected=False |
| sa_core | `us-cw-130` | Entergy Arkansas, Inc | mean_score=0.42857142857142855; visit_count=14; conflict_count=10; is_oc_detected=False |
| sa_core | `us-cw-2080` | System Energy Resources, Inc | mean_score=0.4; visit_count=14; conflict_count=9; is_oc_detected=False |
| sa_core | `us-cw-3379182` | ENTERGY CORP | mean_score=0.5583333333333332; visit_count=24; conflict_count=18; is_oc_detected=False |
| sa_core | `us-cw-822` | ENTERGY GULF STATES INC | mean_score=0.43333333333333335; visit_count=12; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.9464285714285712; visit_count=28; conflict_count=31; is_oc_detected=True |
| naive_subgraph | `us-cw-841126` | Entergy Louisiana Holdings LLC | mean_score=0.36; visit_count=5; conflict_count=0; is_oc_detected=False |
| naive_subgraph | `us-cw-42654` | Entergy Louisiana LLC | mean_score=0.21428571428571427; visit_count=14; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `us-cw-1180` | ENTERGY CORP | mean_score=0.6448275862068966; visit_count=29; conflict_count=37; is_oc_detected=False |
| oc | `us-cw-118216` | ENTERGY LOUISIANA HOLDINGS INC | mean_score=0.9464285714285712; visit_count=28; conflict_count=31; is_oc_detected=True |
