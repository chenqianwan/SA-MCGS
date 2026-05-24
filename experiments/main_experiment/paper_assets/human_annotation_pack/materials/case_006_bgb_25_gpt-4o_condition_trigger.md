# case_006_bgb_25_gpt-4o_condition_trigger: 德国民法法条 / size 25 / gpt-4o

- Template: `condition_trigger` (触发条件前后不一致)
- Root: `bgb_505` — §505 Geduldete Überziehung
- Witness: `bgb_491` — §491 Verbraucherdarlehensvertrag
- Affected nodes: `bgb_506;bgb_358`
- SA core nodes: `bgb_312g;bgb_327m;bgb_327n;bgb_358;bgb_360;bgb_491a;bgb_495;bgb_505;bgb_506;bgb_507;bgb_508;bgb_514`
- Naive subgraph nodes: `bgb_506;bgb_358;bgb_514;bgb_495;bgb_360`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.3076923076923077; visit_count=13; conflict_count=15; is_oc_detected=True |
| witness | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.37; visit_count=10; conflict_count=10; is_oc_detected=True |
| bridge | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.3625; visit_count=16; conflict_count=23; is_oc_detected=False |
| affected | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.3095238095238094; visit_count=21; conflict_count=23; is_oc_detected=False |
| affected | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2739130434782609; visit_count=23; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.2888888888888889; visit_count=9; conflict_count=10; is_oc_detected=False |
| sa_core | `bgb_327m` | §327m Vertragsbeendigung und Schadensersatz | mean_score=0.1875; visit_count=8; conflict_count=9; is_oc_detected=False |
| sa_core | `bgb_327n` | §327n Minderung | mean_score=0.14285714285714285; visit_count=7; conflict_count=4; is_oc_detected=False |
| sa_core | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2739130434782609; visit_count=23; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_360` | §360 Zusammenhängende Verträge | mean_score=0.18571428571428572; visit_count=7; conflict_count=9; is_oc_detected=False |
| sa_core | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.2052631578947369; visit_count=19; conflict_count=22; is_oc_detected=False |
| sa_core | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.3095238095238096; visit_count=21; conflict_count=29; is_oc_detected=True |
| sa_core | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.3076923076923077; visit_count=13; conflict_count=15; is_oc_detected=True |
| sa_core | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.3095238095238094; visit_count=21; conflict_count=23; is_oc_detected=False |
| sa_core | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.32000000000000006; visit_count=10; conflict_count=11; is_oc_detected=False |
| sa_core | `bgb_508` | §508 Rücktritt bei Teilzahlungsgeschäften | mean_score=0.2285714285714286; visit_count=7; conflict_count=5; is_oc_detected=False |
| sa_core | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.3625; visit_count=16; conflict_count=23; is_oc_detected=False |
| naive_subgraph | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.3095238095238094; visit_count=21; conflict_count=23; is_oc_detected=False |
| naive_subgraph | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2739130434782609; visit_count=23; conflict_count=26; is_oc_detected=False |
| naive_subgraph | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.3625; visit_count=16; conflict_count=23; is_oc_detected=False |
| naive_subgraph | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.3095238095238096; visit_count=21; conflict_count=29; is_oc_detected=True |
| naive_subgraph | `bgb_360` | §360 Zusammenhängende Verträge | mean_score=0.18571428571428572; visit_count=7; conflict_count=9; is_oc_detected=False |
| oc | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.37; visit_count=10; conflict_count=10; is_oc_detected=True |
| oc | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.3095238095238096; visit_count=21; conflict_count=29; is_oc_detected=True |
| oc | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.3076923076923077; visit_count=13; conflict_count=15; is_oc_detected=True |
