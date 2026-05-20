# case_022_bgb_11_deepseek-v3_temporal_gate: German Civil Code (BGB) / size 11 / deepseek-v3

- Template: `temporal_gate` (Temporal gate)
- Root: `bgb_311a` — §311a Leistungshindernis bei Vertragsschluss
- Witness: `bgb_280` — §280 Schadensersatz wegen Pflichtverletzung
- Affected nodes: `bgb_326;bgb_281`
- SA core nodes: `bgb_281;bgb_282;bgb_326;bgb_311a;bgb_441`
- Naive subgraph nodes: `bgb_275;bgb_280;bgb_326;bgb_283`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_311a` | §311a Leistungshindernis bei Vertragsschluss | mean_score=0.568; visit_count=25; conflict_count=26; is_oc_detected=False |
| witness | `bgb_280` | §280 Schadensersatz wegen Pflichtverletzung | mean_score=0.508; visit_count=25; conflict_count=14; is_oc_detected=False |
| affected | `bgb_326` | §326 Befreiung von der Gegenleistung und Rücktritt beim Ausschluss der Leistungspflicht | mean_score=0.40000000000000013; visit_count=30; conflict_count=20; is_oc_detected=False |
| affected | `bgb_281` | §281 Schadensersatz statt der Leistung wegen nicht oder nicht wie geschuldet
erbrachter Leistung | mean_score=0.3696969696969697; visit_count=33; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_281` | §281 Schadensersatz statt der Leistung wegen nicht oder nicht wie geschuldet
erbrachter Leistung | mean_score=0.3696969696969697; visit_count=33; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_282` | §282 Schadensersatz statt der Leistung wegen Verletzung einer Pflicht nach §
241 Abs. 2 | mean_score=0.4299999999999999; visit_count=10; conflict_count=8; is_oc_detected=False |
| sa_core | `bgb_326` | §326 Befreiung von der Gegenleistung und Rücktritt beim Ausschluss der Leistungspflicht | mean_score=0.40000000000000013; visit_count=30; conflict_count=20; is_oc_detected=False |
| sa_core | `bgb_311a` | §311a Leistungshindernis bei Vertragsschluss | mean_score=0.568; visit_count=25; conflict_count=26; is_oc_detected=False |
| sa_core | `bgb_441` | §441 Minderung | mean_score=0.30666666666666664; visit_count=15; conflict_count=11; is_oc_detected=False |
| naive_subgraph | `bgb_275` | §275 Ausschluss der Leistungspflicht | mean_score=0.3878787878787879; visit_count=33; conflict_count=26; is_oc_detected=False |
| naive_subgraph | `bgb_280` | §280 Schadensersatz wegen Pflichtverletzung | mean_score=0.508; visit_count=25; conflict_count=14; is_oc_detected=False |
| naive_subgraph | `bgb_326` | §326 Befreiung von der Gegenleistung und Rücktritt beim Ausschluss der Leistungspflicht | mean_score=0.40000000000000013; visit_count=30; conflict_count=20; is_oc_detected=False |
| naive_subgraph | `bgb_283` | §283 Schadensersatz statt der Leistung bei Ausschluss der Leistungspflicht | mean_score=0.34545454545454546; visit_count=22; conflict_count=13; is_oc_detected=False |
| oc | `bgb_346` | §346 Wirkungen des Rücktritts | mean_score=0.4482758620689655; visit_count=29; conflict_count=24; is_oc_detected=True |
