# case_019_bgb_25_gpt-4o_handoff_invariant: German Civil Code (BGB) / size 25 / gpt-4o

- Template: `handoff_invariant` (Handoff invariant)
- Root: `bgb_505` — §505 Geduldete Überziehung
- Witness: `bgb_491` — §491 Verbraucherdarlehensvertrag
- Affected nodes: `bgb_506;bgb_358`
- SA core nodes: `bgb_312g;bgb_327m;bgb_327n;bgb_356;bgb_358;bgb_491a;bgb_495;bgb_505;bgb_504;bgb_506;bgb_507;bgb_514`
- Naive subgraph nodes: `bgb_506;bgb_491;bgb_491a;bgb_508`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.4312500000000001; visit_count=16; conflict_count=23; is_oc_detected=True |
| witness | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.41111111111111115; visit_count=9; conflict_count=9; is_oc_detected=False |
| affected | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.375; visit_count=12; conflict_count=17; is_oc_detected=False |
| affected | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2642857142857143; visit_count=14; conflict_count=17; is_oc_detected=False |
| sa_core | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.3125; visit_count=8; conflict_count=13; is_oc_detected=False |
| sa_core | `bgb_327m` | §327m Vertragsbeendigung und Schadensersatz | mean_score=0.24285714285714288; visit_count=7; conflict_count=10; is_oc_detected=False |
| sa_core | `bgb_327n` | §327n Minderung | mean_score=0.21250000000000002; visit_count=8; conflict_count=10; is_oc_detected=False |
| sa_core | `bgb_356` | §356 Widerrufsrecht bei außerhalb von Geschäftsräumen geschlossenen Verträgen und Fernabsatzverträgen | mean_score=0.15999999999999998; visit_count=5; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2642857142857143; visit_count=14; conflict_count=17; is_oc_detected=False |
| sa_core | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.24615384615384617; visit_count=26; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.2923076923076923; visit_count=26; conflict_count=37; is_oc_detected=False |
| sa_core | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.4312500000000001; visit_count=16; conflict_count=23; is_oc_detected=True |
| sa_core | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.37368421052631573; visit_count=19; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.375; visit_count=12; conflict_count=17; is_oc_detected=False |
| sa_core | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.35714285714285715; visit_count=7; conflict_count=10; is_oc_detected=False |
| sa_core | `bgb_514` | §514 Unentgeltliche Darlehensverträge | mean_score=0.29; visit_count=10; conflict_count=9; is_oc_detected=False |
| naive_subgraph | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.375; visit_count=12; conflict_count=17; is_oc_detected=False |
| naive_subgraph | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.41111111111111115; visit_count=9; conflict_count=9; is_oc_detected=False |
| naive_subgraph | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.24615384615384617; visit_count=26; conflict_count=26; is_oc_detected=False |
| naive_subgraph | `bgb_508` | §508 Rücktritt bei Teilzahlungsgeschäften | mean_score=0.25; visit_count=4; conflict_count=1; is_oc_detected=False |
| oc | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.4312500000000001; visit_count=16; conflict_count=23; is_oc_detected=True |
