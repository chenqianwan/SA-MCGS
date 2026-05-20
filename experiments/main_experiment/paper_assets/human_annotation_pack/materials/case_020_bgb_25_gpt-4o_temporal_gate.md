# case_020_bgb_25_gpt-4o_temporal_gate: German Civil Code (BGB) / size 25 / gpt-4o

- Template: `temporal_gate` (Temporal gate)
- Root: `bgb_505` — §505 Geduldete Überziehung
- Witness: `bgb_491` — §491 Verbraucherdarlehensvertrag
- Affected nodes: `bgb_506;bgb_358`
- SA core nodes: `bgb_312g;bgb_327m;bgb_327n;bgb_358;bgb_491a;bgb_495;bgb_505;bgb_504;bgb_506;bgb_507;bgb_508;bgb_514`
- Naive subgraph nodes: `bgb_506;bgb_491;bgb_495;bgb_508`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.37000000000000005; visit_count=20; conflict_count=19; is_oc_detected=True |
| witness | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.4272727272727273; visit_count=11; conflict_count=14; is_oc_detected=False |
| affected | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4166666666666666; visit_count=12; conflict_count=17; is_oc_detected=False |
| affected | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.30714285714285705; visit_count=28; conflict_count=22; is_oc_detected=False |
| sa_core | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.37500000000000006; visit_count=8; conflict_count=11; is_oc_detected=False |
| sa_core | `bgb_327m` | §327m Vertragsbeendigung und Schadensersatz | mean_score=0.31111111111111106; visit_count=9; conflict_count=12; is_oc_detected=False |
| sa_core | `bgb_327n` | §327n Minderung | mean_score=0.18333333333333332; visit_count=6; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.30714285714285705; visit_count=28; conflict_count=22; is_oc_detected=False |
| sa_core | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.25833333333333336; visit_count=12; conflict_count=15; is_oc_detected=False |
| sa_core | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.284; visit_count=25; conflict_count=41; is_oc_detected=False |
| sa_core | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.37000000000000005; visit_count=20; conflict_count=19; is_oc_detected=True |
| sa_core | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.30500000000000005; visit_count=20; conflict_count=19; is_oc_detected=False |
| sa_core | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4166666666666666; visit_count=12; conflict_count=17; is_oc_detected=False |
| sa_core | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.49999999999999994; visit_count=7; conflict_count=14; is_oc_detected=True |
| sa_core | `bgb_508` | §508 Rücktritt bei Teilzahlungsgeschäften | mean_score=0.27499999999999997; visit_count=4; conflict_count=6; is_oc_detected=False |
| sa_core | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.38; visit_count=10; conflict_count=15; is_oc_detected=False |
| naive_subgraph | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4166666666666666; visit_count=12; conflict_count=17; is_oc_detected=False |
| naive_subgraph | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.4272727272727273; visit_count=11; conflict_count=14; is_oc_detected=False |
| naive_subgraph | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.284; visit_count=25; conflict_count=41; is_oc_detected=False |
| naive_subgraph | `bgb_508` | §508 Rücktritt bei Teilzahlungsgeschäften | mean_score=0.27499999999999997; visit_count=4; conflict_count=6; is_oc_detected=False |
| oc | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.37000000000000005; visit_count=20; conflict_count=19; is_oc_detected=True |
| oc | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.49999999999999994; visit_count=7; conflict_count=14; is_oc_detected=True |
