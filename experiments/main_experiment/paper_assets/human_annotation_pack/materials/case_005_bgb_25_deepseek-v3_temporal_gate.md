# case_005_bgb_25_deepseek-v3_temporal_gate: 德国民法法条 / size 25 / deepseek-v3

- Template: `temporal_gate` (时间或生效顺序冲突)
- Root: `bgb_505` — §505 Geduldete Überziehung
- Witness: `bgb_491` — §491 Verbraucherdarlehensvertrag
- Affected nodes: `bgb_506;bgb_358`
- SA core nodes: `bgb_312g;bgb_327;bgb_327b;bgb_327n;bgb_327o;bgb_491a;bgb_495;bgb_505;bgb_504;bgb_506;bgb_507;bgb_513`
- Naive subgraph nodes: `bgb_495;bgb_491a;bgb_491;bgb_358;bgb_312g;bgb_506;bgb_504;bgb_356;bgb_514;bgb_505`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.5999999999999999; visit_count=7; conflict_count=9; is_oc_detected=True |
| witness | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.4461538461538461; visit_count=13; conflict_count=8; is_oc_detected=True |
| bridge | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.3222222222222222; visit_count=9; conflict_count=5; is_oc_detected=False |
| affected | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4769230769230769; visit_count=13; conflict_count=12; is_oc_detected=False |
| affected | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.41538461538461535; visit_count=13; conflict_count=8; is_oc_detected=False |
| sa_core | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.32999999999999996; visit_count=20; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_327` | §327 Anwendungsbereich | mean_score=0.423529411764706; visit_count=17; conflict_count=18; is_oc_detected=True |
| sa_core | `bgb_327b` | §327b Bereitstellung digitaler Produkte | mean_score=0.19999999999999998; visit_count=10; conflict_count=2; is_oc_detected=False |
| sa_core | `bgb_327n` | §327n Minderung | mean_score=0.32857142857142857; visit_count=7; conflict_count=8; is_oc_detected=False |
| sa_core | `bgb_327o` | §327o Erklärung und Rechtsfolgen der Vertragsbeendigung | mean_score=0.3375; visit_count=8; conflict_count=4; is_oc_detected=False |
| sa_core | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.3428571428571428; visit_count=14; conflict_count=19; is_oc_detected=False |
| sa_core | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.3916666666666666; visit_count=12; conflict_count=10; is_oc_detected=False |
| sa_core | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.5999999999999999; visit_count=7; conflict_count=9; is_oc_detected=True |
| sa_core | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.4727272727272727; visit_count=11; conflict_count=10; is_oc_detected=True |
| sa_core | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4769230769230769; visit_count=13; conflict_count=12; is_oc_detected=False |
| sa_core | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.52; visit_count=10; conflict_count=9; is_oc_detected=True |
| sa_core | `bgb_513` | §513 Anwendung auf Existenzgründer | mean_score=0.27999999999999997; visit_count=5; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.3916666666666666; visit_count=12; conflict_count=10; is_oc_detected=False |
| naive_subgraph | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.3428571428571428; visit_count=14; conflict_count=19; is_oc_detected=False |
| naive_subgraph | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.4461538461538461; visit_count=13; conflict_count=8; is_oc_detected=True |
| naive_subgraph | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.41538461538461535; visit_count=13; conflict_count=8; is_oc_detected=False |
| naive_subgraph | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.32999999999999996; visit_count=20; conflict_count=7; is_oc_detected=False |
| naive_subgraph | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.4769230769230769; visit_count=13; conflict_count=12; is_oc_detected=False |
| naive_subgraph | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.4727272727272727; visit_count=11; conflict_count=10; is_oc_detected=True |
| naive_subgraph | `bgb_356` | §356 Widerrufsrecht bei außerhalb von Geschäftsräumen geschlossenen Verträgen und Fernabsatzverträgen | mean_score=0.39999999999999997; visit_count=5; conflict_count=2; is_oc_detected=False |
| naive_subgraph | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.3222222222222222; visit_count=9; conflict_count=5; is_oc_detected=False |
| naive_subgraph | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.5999999999999999; visit_count=7; conflict_count=9; is_oc_detected=True |
| oc | `bgb_327` | §327 Anwendungsbereich | mean_score=0.423529411764706; visit_count=17; conflict_count=18; is_oc_detected=True |
| oc | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.4461538461538461; visit_count=13; conflict_count=8; is_oc_detected=True |
| oc | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.4727272727272727; visit_count=11; conflict_count=10; is_oc_detected=True |
| oc | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.5999999999999999; visit_count=7; conflict_count=9; is_oc_detected=True |
| oc | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.52; visit_count=10; conflict_count=9; is_oc_detected=True |
