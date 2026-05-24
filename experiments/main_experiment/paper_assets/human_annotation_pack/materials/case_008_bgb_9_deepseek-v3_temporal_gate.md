# case_008_bgb_9_deepseek-v3_temporal_gate: 德国民法法条 / size 9 / deepseek-v3

- Template: `temporal_gate` (时间或生效顺序冲突)
- Root: `bgb_559e` — §559e Mieterhöhung nach Einbau oder Aufstellung einer Heizungsanlage
- Witness: `bgb_558` — §558 Mieterhöhung bis zur ortsüblichen Vergleichsmiete
- Affected nodes: `bgb_555c;bgb_559a`
- SA core nodes: `bgb_555c;bgb_555d;bgb_559;bgb_559b;bgb_559c`
- Naive subgraph nodes: `bgb_555c;bgb_555d;bgb_559;bgb_559b`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_559e` | §559e Mieterhöhung nach Einbau oder Aufstellung einer Heizungsanlage | mean_score=0.5083333333333333; visit_count=36; conflict_count=40; is_oc_detected=False |
| witness | `bgb_558` | §558 Mieterhöhung bis zur ortsüblichen Vergleichsmiete | mean_score=0.38; visit_count=10; conflict_count=6; is_oc_detected=False |
| bridge | `bgb_555d` | §555d Duldung von Modernisierungsmaßnahmen, Ausschlussfrist | mean_score=0.4058823529411764; visit_count=17; conflict_count=13; is_oc_detected=False |
| affected | `bgb_555c` | §555c Ankündigung von Modernisierungsmaßnahmen | mean_score=0.35; visit_count=40; conflict_count=29; is_oc_detected=False |
| affected | `bgb_559a` | §559a Anrechnung von Drittmitteln | mean_score=0.27058823529411763; visit_count=17; conflict_count=7; is_oc_detected=False |
| sa_core | `bgb_555c` | §555c Ankündigung von Modernisierungsmaßnahmen | mean_score=0.35; visit_count=40; conflict_count=29; is_oc_detected=False |
| sa_core | `bgb_555d` | §555d Duldung von Modernisierungsmaßnahmen, Ausschlussfrist | mean_score=0.4058823529411764; visit_count=17; conflict_count=13; is_oc_detected=False |
| sa_core | `bgb_559` | §559 Mieterhöhung nach Modernisierungsmaßnahmen | mean_score=0.4222222222222222; visit_count=45; conflict_count=49; is_oc_detected=False |
| sa_core | `bgb_559b` | §559b Geltendmachung der Erhöhung, Wirkung der Erhöhungserklärung | mean_score=0.32941176470588235; visit_count=17; conflict_count=6; is_oc_detected=False |
| sa_core | `bgb_559c` | §559c Vereinfachtes Verfahren | mean_score=0.6133333333333334; visit_count=45; conflict_count=73; is_oc_detected=True |
| naive_subgraph | `bgb_555c` | §555c Ankündigung von Modernisierungsmaßnahmen | mean_score=0.35; visit_count=40; conflict_count=29; is_oc_detected=False |
| naive_subgraph | `bgb_555d` | §555d Duldung von Modernisierungsmaßnahmen, Ausschlussfrist | mean_score=0.4058823529411764; visit_count=17; conflict_count=13; is_oc_detected=False |
| naive_subgraph | `bgb_559` | §559 Mieterhöhung nach Modernisierungsmaßnahmen | mean_score=0.4222222222222222; visit_count=45; conflict_count=49; is_oc_detected=False |
| naive_subgraph | `bgb_559b` | §559b Geltendmachung der Erhöhung, Wirkung der Erhöhungserklärung | mean_score=0.32941176470588235; visit_count=17; conflict_count=6; is_oc_detected=False |
| oc | `bgb_559c` | §559c Vereinfachtes Verfahren | mean_score=0.6133333333333334; visit_count=45; conflict_count=73; is_oc_detected=True |
