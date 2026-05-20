# case_023_bgb_11_gpt-4o_temporal_gate: German Civil Code (BGB) / size 11 / gpt-4o

- Template: `temporal_gate` (Temporal gate)
- Root: `bgb_311a` — §311a Leistungshindernis bei Vertragsschluss
- Witness: `bgb_280` — §280 Schadensersatz wegen Pflichtverletzung
- Affected nodes: `bgb_326;bgb_281`
- SA core nodes: `bgb_275;bgb_280;bgb_281;bgb_282;bgb_283`
- Naive subgraph nodes: `bgb_326;bgb_275;bgb_283;bgb_311a`

## Annotation Task / 标注任务

EN: Judge whether the listed root/witness/affected nodes form a real structural risk, and whether the SA core is sufficient as a repair-oriented risk subgraph.

中文：判断 root/witness/affected 是否形成真实结构风险，以及 SA core 是否足够作为可修复的风险子图。

## Node Evidence

| Role | Node | Label | Stats |
|---|---|---|---|
| root | `bgb_311a` | §311a Leistungshindernis bei Vertragsschluss | mean_score=0.5933333333333334; visit_count=15; conflict_count=24; is_oc_detected=False |
| witness | `bgb_280` | §280 Schadensersatz wegen Pflichtverletzung | mean_score=0.6184210526315789; visit_count=38; conflict_count=52; is_oc_detected=False |
| affected | `bgb_326` | §326 Befreiung von der Gegenleistung und Rücktritt beim Ausschluss der Leistungspflicht | mean_score=0.2111111111111111; visit_count=18; conflict_count=16; is_oc_detected=False |
| affected | `bgb_281` | §281 Schadensersatz statt der Leistung wegen nicht oder nicht wie geschuldet
erbrachter Leistung | mean_score=0.6029411764705881; visit_count=34; conflict_count=54; is_oc_detected=False |
| sa_core | `bgb_275` | §275 Ausschluss der Leistungspflicht | mean_score=0.3727272727272727; visit_count=22; conflict_count=29; is_oc_detected=False |
| sa_core | `bgb_280` | §280 Schadensersatz wegen Pflichtverletzung | mean_score=0.6184210526315789; visit_count=38; conflict_count=52; is_oc_detected=False |
| sa_core | `bgb_281` | §281 Schadensersatz statt der Leistung wegen nicht oder nicht wie geschuldet
erbrachter Leistung | mean_score=0.6029411764705881; visit_count=34; conflict_count=54; is_oc_detected=False |
| sa_core | `bgb_282` | §282 Schadensersatz statt der Leistung wegen Verletzung einer Pflicht nach §
241 Abs. 2 | mean_score=0.625; visit_count=12; conflict_count=15; is_oc_detected=False |
| sa_core | `bgb_283` | §283 Schadensersatz statt der Leistung bei Ausschluss der Leistungspflicht | mean_score=0.521875; visit_count=32; conflict_count=44; is_oc_detected=False |
| naive_subgraph | `bgb_326` | §326 Befreiung von der Gegenleistung und Rücktritt beim Ausschluss der Leistungspflicht | mean_score=0.2111111111111111; visit_count=18; conflict_count=16; is_oc_detected=False |
| naive_subgraph | `bgb_275` | §275 Ausschluss der Leistungspflicht | mean_score=0.3727272727272727; visit_count=22; conflict_count=29; is_oc_detected=False |
| naive_subgraph | `bgb_283` | §283 Schadensersatz statt der Leistung bei Ausschluss der Leistungspflicht | mean_score=0.521875; visit_count=32; conflict_count=44; is_oc_detected=False |
| naive_subgraph | `bgb_311a` | §311a Leistungshindernis bei Vertragsschluss | mean_score=0.5933333333333334; visit_count=15; conflict_count=24; is_oc_detected=False |
