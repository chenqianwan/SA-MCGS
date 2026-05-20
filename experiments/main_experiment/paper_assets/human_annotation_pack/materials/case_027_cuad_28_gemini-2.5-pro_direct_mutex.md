# case_027_cuad_28_gemini-2.5-pro_direct_mutex: CUAD contracts / size 28 / gemini-2.5-pro

- Template: `direct_mutex` (Direct mutual exclusion)
- Root: `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.1` — MSL will not copy or permit the copying (including back-up copies) of all     or any part of the IBM Software Packages, except to the extent required for     MSL to perform its obligations hereunder for IBM's benefit;
- Witness: `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.1` — When authorized by IBM in writing or expressly instructed under this     Attachment 6, MSL agrees to prepare the IBM Software Package Preload image     in support of Products.
- Affected nodes: `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.2;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__16`
- SA core nodes: `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__1.4;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__10;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__16;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__17;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__4;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__4.0`
- Naive subgraph nodes: `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.1;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.1;cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.2`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.1` | MSL will not copy or permit the copying (including back-up copies) of all     or any part of the IBM Software Packages, except to the extent required for     MSL to perform its obligations hereunder for IBM's benefit; | mean_score=0.78; visit_count=5; conflict_count=4; is_oc_detected=False |
| witness | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.1` | When authorized by IBM in writing or expressly instructed under this     Attachment 6, MSL agrees to prepare the IBM Software Package Preload image     in support of Products. | mean_score=0.375; visit_count=12; conflict_count=1; is_oc_detected=False |
| affected | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.2` | MSL will not sublicense, rent, lease, distribute, assign or otherwise transfer (including distributing back-up copies of) all or any part of the IBM Software Packages, except as expressly authorized by IBM in writing; | mean_score=0.0; visit_count=3; conflict_count=0; is_oc_detected=False |
| affected | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__16` | 0 PACKAGING | mean_score=0.5714285714285714; visit_count=21; conflict_count=17; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__1.4` | MS APPROVAL | mean_score=0.39999999999999997; visit_count=6; conflict_count=1; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__10` | 5  Shipment Terms | mean_score=0.46666666666666656; visit_count=12; conflict_count=10; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__16` | 0 PACKAGING | mean_score=0.5714285714285714; visit_count=21; conflict_count=17; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__17` | 3  MSL Support for IBM Customer Warranty | mean_score=0.5714285714285714; visit_count=21; conflict_count=13; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2` | 2 | mean_score=0.7045454545454546; visit_count=22; conflict_count=21; is_oc_detected=True |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__4` | ADDITIONAL AUDITS AND INSPECTIONS. | mean_score=0.47000000000000003; visit_count=10; conflict_count=5; is_oc_detected=False |
| sa_core | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__4.0` | ADDITIONAL AUDIT RIGHTS | mean_score=0.3636363636363636; visit_count=11; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.1` | When authorized by IBM in writing or expressly instructed under this     Attachment 6, MSL agrees to prepare the IBM Software Package Preload image     in support of Products. | mean_score=0.375; visit_count=12; conflict_count=1; is_oc_detected=False |
| naive_subgraph | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__3.1` | MSL will not copy or permit the copying (including back-up copies) of all     or any part of the IBM Software Packages, except to the extent required for     MSL to perform its obligations hereunder for IBM's benefit; | mean_score=0.78; visit_count=5; conflict_count=4; is_oc_detected=False |
| naive_subgraph | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2.2` | MSL agrees to Preload IBM Software Packages (only at Approved Locations) on     Products as set forth in this Attachment 6. | mean_score=0.38095238095238093; visit_count=21; conflict_count=1; is_oc_detected=False |
| oc | `cuad_MANUFACTURERSSERVICESLTD_06_05_2000_EX_1__cuad_MANUFACTURERSSERVICESLTD_06_05_2000__dccdb230__2` | 2 | mean_score=0.7045454545454546; visit_count=22; conflict_count=21; is_oc_detected=True |
