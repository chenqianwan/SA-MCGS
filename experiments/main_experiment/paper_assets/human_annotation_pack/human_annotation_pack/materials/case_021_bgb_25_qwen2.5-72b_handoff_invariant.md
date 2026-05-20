# case_021_bgb_25_qwen2.5-72b_handoff_invariant: German Civil Code (BGB) / size 25 / qwen2.5-72b

- Template: `handoff_invariant` (Handoff invariant)
- Root: `bgb_505` — §505 Geduldete Überziehung
- Witness: `bgb_491` — §491 Verbraucherdarlehensvertrag
- Affected nodes: `bgb_506;bgb_358`
- SA core nodes: `bgb_312f;bgb_312g;bgb_327m;bgb_327n;bgb_327o;bgb_356;bgb_491a;bgb_495;bgb_505;bgb_504;bgb_506;bgb_507`
- Naive subgraph nodes: `-`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.3571428571428571; visit_count=7; conflict_count=7; is_oc_detected=False |
| witness | `bgb_491` | §491 Verbraucherdarlehensvertrag | mean_score=0.24210526315789477; visit_count=19; conflict_count=7; is_oc_detected=False |
| affected | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.31666666666666665; visit_count=18; conflict_count=22; is_oc_detected=True |
| affected | `bgb_358` | §358 Mit dem widerrufenen Vertrag verbundener Vertrag | mean_score=0.2416666666666667; visit_count=12; conflict_count=9; is_oc_detected=False |
| sa_core | `bgb_312f` | §312f Abschriften und Bestätigungen | mean_score=0.13333333333333333; visit_count=6; conflict_count=4; is_oc_detected=False |
| sa_core | `bgb_312g` | §312g Widerrufsrecht | mean_score=0.19411764705882356; visit_count=17; conflict_count=6; is_oc_detected=False |
| sa_core | `bgb_327m` | §327m Vertragsbeendigung und Schadensersatz | mean_score=0.18749999999999997; visit_count=8; conflict_count=5; is_oc_detected=False |
| sa_core | `bgb_327n` | §327n Minderung | mean_score=0.19999999999999998; visit_count=8; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_327o` | §327o Erklärung und Rechtsfolgen der Vertragsbeendigung | mean_score=0.18888888888888888; visit_count=9; conflict_count=6; is_oc_detected=False |
| sa_core | `bgb_356` | §356 Widerrufsrecht bei außerhalb von Geschäftsräumen geschlossenen Verträgen und Fernabsatzverträgen | mean_score=0.20000000000000004; visit_count=6; conflict_count=4; is_oc_detected=False |
| sa_core | `bgb_491a` | §491a Vorvertragliche Informationspflichten bei Verbraucherdarlehensverträgen | mean_score=0.16800000000000004; visit_count=25; conflict_count=15; is_oc_detected=False |
| sa_core | `bgb_495` | §495 Widerrufsrecht; Bedenkzeit | mean_score=0.2785714285714286; visit_count=14; conflict_count=13; is_oc_detected=False |
| sa_core | `bgb_505` | §505 Geduldete Überziehung | mean_score=0.3571428571428571; visit_count=7; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_504` | §504 Eingeräumte Überziehungsmöglichkeit | mean_score=0.25; visit_count=8; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.31666666666666665; visit_count=18; conflict_count=22; is_oc_detected=True |
| sa_core | `bgb_507` | §507 Teilzahlungsgeschäfte | mean_score=0.13333333333333333; visit_count=6; conflict_count=5; is_oc_detected=False |
| oc | `bgb_506` | §506 Zahlungsaufschub, sonstige Finanzierungshilfe | mean_score=0.31666666666666665; visit_count=18; conflict_count=22; is_oc_detected=True |
