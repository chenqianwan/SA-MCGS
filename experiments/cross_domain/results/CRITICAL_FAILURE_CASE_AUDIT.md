# Critical Risk-Subgraph Failure Case 内容审计

结果来源：`severitygrid_cuad_bgb_2size_b60_severity_grid_status.json`

## Executive conclusion

- Critical SA-MCGS 总 case：`32`；长环 case（actual SCC >= 18）：`24`。
- 长环里 `risk-any` 失败：`5/24`；`risk-all` 失败：`16/24`。
- 最重要结论：失败大多不是模型完全没看到风险。5 个 risk-any 失败中，风险节点都曾进入 window/local/context，问题集中在 final core compression 阶段。
- 因此当前算法瓶颈不是继续扩大 prompt，而是 OC/local/context evidence 到 final core 的 retention policy。
- `risk-all` 不应作为唯一主指标。结构性缺陷可以通过 root、witness、bridge 或 affected 节点修复，完整收齐所有端点是严格上界。

## 1. Critical 失败概览

| Group | N | Risk-any fail | Risk-all fail | risk seen in local | risk in context but dropped | affected in core | avg compression |
|---|---:|---:|---:|---:|---:|---:|---:|
| BGB-25 | 8 | 3/8 | 8/8 | 8/8 | 3/8 | 2/8 | 88% |
| CUAD-18 | 8 | 2/8 | 5/8 | 8/8 | 2/8 | 5/8 | 78% |
| CUAD-25 | 8 | 0/8 | 3/8 | 8/8 | 0/8 | 2/8 | 83% |
| All long critical | 24 | 5/24 | 16/24 | 24/24 | 5/24 | 9/24 | 83% |

Failure mode counts for long critical cases:

- `Context Has It, Core Drops It`: `5`
- `Success: risk-all retained`: `8`
- `Risk-all Too Strict`: `11`

- Failure mode 图：[critical_failure_modes.png](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/critical_failure_modes.png)
- Case evidence matrix：[critical_case_evidence_matrix.png](/Users/chenlong/.codex/worktrees/9c5f/MCGS_Law/experiments/cross_domain/results/figures/critical_case_evidence_matrix.png)

## 2. 5 个 risk-any 失败 case 深挖

这 5 个 case 的共同点是：risk endpoints 并非完全不可见，而是被 local/context 捕获后没有留在 final core。

### Case F1. CUAD-18 `direct_mutex` `gpt-4o`

- **Failure mode:** Context Has It, Core Drops It；tags: `context_has_risk_but_core_drops, scored_or_declared_then_outcompeted`。
- **Rollout timeline:** window@`2`, local@`2`, prefix-core@`2`, effective-OC@`43`。
- **Final core:** ['8.3', '13']；stop=`score_gap`；compression=`89%`；context size=`9`。
- **OC nodes:** ['2', '13']；top non-risk distractors: ['13', '16.6', '8.3', '21']。

| Role | Node | Text snapshot | Injected patch / evidence stats |
|---|---|---|---|
| risk/root-witness | `2` 1 The Advanced Pool Stock is composed of items defined in Exhibit 16 ("Advanced Pool Stock"), which may be either brand new items or Used Serviceable Items depending on availability of each item of the Advanced Pool Stock into Repairer's inventory at the time of their respective delivery. | 1 The Advanced Pool Stock is composed of items defined in Exhibit 16 ("Advanced Pool Stock"), which may be either brand new items or Used Serviceable Items depending on availability of each item of the Advanced Pool Stock into Repairer's inventory at the time of their respective delivery. | The same termination path requires payment of an early termination fee before the 30 day notice can become effective. This record makes the opposite status immediately operative on that same path and treats any upstream mismatch as a material default with payment acceleration and loss ...<br><br>`mean=0.82, max=1.00, visit=9, conflicts=13, evidence=0.47, priority=0.79, rel=0.62, pair=0.67, selected=False` |
| risk/root-witness | `9` Warranties | Warranties | The customer may terminate for convenience on 30 days notice without paying any early termination fee on this path. This status is non-waivable on the same transaction path. A contrary downstream treatment leaves no cure window, automatically suspends performance, accelerates all unpaid amounts, and triggers ...<br><br>`mean=0.83, max=1.00, visit=10, conflicts=15, evidence=0.38, priority=0.54, rel=0.42, pair=0.65, selected=False` |
| affected | `23` 23 | 23 | mean=0.81, max=1.00, visit=7, conflicts=7, evidence=0.27, priority=0.39, rel=0.31, pair=0.52, selected=False |
| affected | `1` 1 | 1 | mean=0.73, max=0.90, visit=10, conflicts=11, evidence=0.24, priority=0.39, rel=0.31, pair=0.63, selected=False |
| final-core non-risk | `8.3` The Company may not, under any circumstances, perform or permit any action to be taken that   [*****] Confidential material redacted and filed separately with the Securities and Exchange Commission.   AZUL-ATR   Global Maintenance Master Agreement DS/CS-3957/14/Issue 7   Page 105/110 | The Company may not, under any circumstances, perform or permit any action to be taken that [*****] Confidential material redacted and filed separately with the Securities and Exchange Commission. AZUL-ATR Global Maintenance Master Agreement DS/CS-3957/14/Issue 7 Page 105/110 | mean=0.69, max=0.90, visit=29, conflicts=44, evidence=0.57, priority=0.77, rel=0.60, pair=0.82, selected=True |
| final-core non-risk | `13` 1 As per provisions of Clause 17 ("Conditions precedent"), and unless otherwise agreed by the Parties, the Company shall pay the Security Deposit to the Repairer in an amount equal to the aggregate of:     (i) [*****], as per Exhibit 14 ("Price conditions"); and,     (ii) [*****] of the value of the Stock. | 1 As per provisions of Clause 17 ("Conditions precedent"), and unless otherwise agreed by the Parties, the Company shall pay the Security Deposit to the Repairer in an amount equal to the aggregate of: (i) [*****], as per Exhibit 14 ("Price conditions"); and, (ii) [*****] of the value of the Stock. | mean=0.74, max=1.00, visit=29, conflicts=65, evidence=0.92, priority=1.28, rel=1.00, pair=0.82, selected=True |

**诊断。** 风险端点 ['2', '9'] 已经进入 local/context 证据，但 final core 在 `score_gap` 处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。

### Case F2. CUAD-18 `direct_mutex` `deepseek-v3`

- **Failure mode:** Context Has It, Core Drops It；tags: `context_has_risk_but_core_drops, affected_or_diffuse_region_selected, oc_mislocalized, scored_or_declared_then_outcompeted`。
- **Rollout timeline:** window@`2`, local@`2`, prefix-core@`2`, effective-OC@`None`。
- **Final core:** ['7', '21', '5.2', '1']；stop=`score_gap`；compression=`78%`；context size=`9`。
- **OC nodes:** ['7']；top non-risk distractors: ['21', '7', '5.2', '13']。

| Role | Node | Text snapshot | Injected patch / evidence stats |
|---|---|---|---|
| risk/root-witness | `2` 1 The Advanced Pool Stock is composed of items defined in Exhibit 16 ("Advanced Pool Stock"), which may be either brand new items or Used Serviceable Items depending on availability of each item of the Advanced Pool Stock into Repairer's inventory at the time of their respective delivery. | 1 The Advanced Pool Stock is composed of items defined in Exhibit 16 ("Advanced Pool Stock"), which may be either brand new items or Used Serviceable Items depending on availability of each item of the Advanced Pool Stock into Repairer's inventory at the time of their respective delivery. | The same termination path requires payment of an early termination fee before the 30 day notice can become effective. This record makes the opposite status immediately operative on that same path and treats any upstream mismatch as a material default with payment acceleration and loss ...<br><br>`mean=0.76, max=0.90, visit=8, conflicts=13, evidence=0.37, priority=0.54, rel=0.55, pair=0.69, selected=False` |
| risk/root-witness | `9` Warranties | Warranties | The customer may terminate for convenience on 30 days notice without paying any early termination fee on this path. This status is non-waivable on the same transaction path. A contrary downstream treatment leaves no cure window, automatically suspends performance, accelerates all unpaid amounts, and triggers ...<br><br>`mean=0.72, max=0.80, visit=8, conflicts=5, evidence=0.23, priority=0.39, rel=0.40, pair=0.64, selected=False` |
| affected | `23` 23 | 23 | mean=0.74, max=1.00, visit=30, conflicts=16, evidence=0.50, priority=0.62, rel=0.64, pair=0.53, selected=False |
| affected | `1` 1 | 1 | mean=0.73, max=0.90, visit=29, conflicts=38, evidence=0.81, priority=0.98, rel=1.00, pair=0.71, selected=True |
| final-core non-risk | `7` 7 | 7 | mean=0.80, max=0.90, visit=13, conflicts=15, evidence=0.58, priority=0.88, rel=0.89, pair=0.57, selected=True |
| final-core non-risk | `21` TAXES | TAXES | mean=0.66, max=0.90, visit=31, conflicts=37, evidence=0.60, priority=0.77, rel=0.78, pair=0.71, selected=True |
| final-core non-risk | `5.2` 3 Audit of the Repair | 3 Audit of the Repair | mean=0.62, max=0.90, visit=24, conflicts=24, evidence=0.41, priority=0.58, rel=0.59, pair=0.71, selected=True |

**诊断。** 风险端点 ['2', '9'] 已经进入 local/context 证据，但 final core 在 `score_gap` 处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。

### Case F3. BGB-25 `direct_mutex` `deepseek-v3`

- **Failure mode:** Context Has It, Core Drops It；tags: `context_has_risk_but_core_drops, oc_mislocalized, scored_or_declared_then_outcompeted`。
- **Rollout timeline:** window@`7`, local@`7`, prefix-core@`12`, effective-OC@`None`。
- **Final core:** ['§514', '§312g']；stop=`score_gap`；compression=`92%`；context size=`12`。
- **OC nodes:** ['§514']；top non-risk distractors: ['§514', '§495', '§312g', '§504']。

| Role | Node | Text snapshot | Injected patch / evidence stats |
|---|---|---|---|
| risk/root-witness | `§505` §505 Geduldete Überziehung | (1) Vereinbart ein Unternehmer in einem Vertrag mit einem Verbraucher über ein laufendes Konto ohne eingeräumte Überziehungsmöglichkeit ein Entgelt für den Fall, dass er eine Überziehung des Kontos duldet, müssen in diesem Vertrag die Angaben nach Artikel 247 § 17 Abs. 1 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche auf einem dauerhaften Datenträger enthalten sein und dem ... | A party that cures the stated obligation within three months is treated as timely and faces no additional burden on this path. This classification is mandatory for the same obligation path. A contrary downstream treatment would make the same debtor both released from the burden ...<br><br>`mean=0.52, max=0.70, visit=5, conflicts=8, evidence=0.29, priority=0.42, rel=0.33, pair=0.53, selected=False` |
| risk/root-witness | `§491` §491 Verbraucherdarlehensvertrag | (1) Die Vorschriften dieses Kapitels gelten für Verbraucherdarlehensverträge, soweit nichts anderes bestimmt ist. Verbraucherdarlehensverträge sind Allgemein-Verbraucherdarlehensverträge und Immobiliar-Verbraucherdarlehensverträge.(2) Allgemein-Verbraucherdarlehensverträge sind entgeltliche Darlehensverträge zwischen einem Unternehmer als Darlehensgeber und einem Verbraucher als Darlehensnehmer. Keine Allgemein-Verbraucherdarlehensverträge sind Verträge, 1.bei denen der Nettodarlehensbetrag (Artikel 247 § 3 Abs. 2 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche) weniger als 200 Euro ... | The same path requires a party that cures within three months to pay an additional 20 percent charge before the cure is accepted. This record applies the opposite remedy class immediately on the same obligation path, creating a non-curable enforcement conflict if the upstream classification ...<br><br>`mean=0.42, max=0.80, visit=18, conflicts=11, evidence=0.35, priority=0.48, rel=0.38, pair=0.58, selected=False` |
| affected | `§506` §506 Zahlungsaufschub, sonstige Finanzierungshilfe | (1) Die für Allgemein-Verbraucherdarlehensverträge geltenden Vorschriften der §§ 358 bis 360 und 491a bis 502 sowie 505a bis 505e sind mit Ausnahme des § 492 Abs. 4 und vorbehaltlich der Absätze 3 und 4 auf Verträge entsprechend anzuwenden, durch die ein Unternehmer einem Verbraucher einen entgeltlichen Zahlungsaufschub oder eine sonstige entgeltliche Finanzierungshilfe gewährt. Bezieht sich ... | mean=0.46, max=0.80, visit=9, conflicts=5, evidence=0.23, priority=0.40, rel=0.31, pair=0.68, selected=False |
| affected | `§358` §358 Mit dem widerrufenen Vertrag verbundener Vertrag | (1) Hat der Verbraucher seine auf den Abschluss eines Vertrags über die Lieferung einer Ware oder die Erbringung einer anderen Leistung durch einen Unternehmer gerichtete Willenserklärung wirksam widerrufen, so ist er auch an seine auf den Abschluss eines mit diesem Vertrag verbundenen Darlehensvertrags gerichtete Willenserklärung nicht mehr gebunden.(2) Hat der Verbraucher seine auf den Abschluss ... | mean=0.48, max=0.80, visit=9, conflicts=5, evidence=0.20, priority=0.33, rel=0.26, pair=0.53, selected=False |
| final-core non-risk | `§514` §514 Unentgeltliche Darlehensverträge | (1) § 497 Absatz 1 und 3 sowie § 498 und die §§ 505a bis 505c sowie 505d Absatz 2 und 3 sowie § 505e sind entsprechend auf Verträge anzuwenden, durch die ein Unternehmer einem Verbraucher ein unentgeltliches Darlehen gewährt. Dies gilt nicht in dem in § 491 Absatz 2 Satz 2 Nummer 1 bestimmten ... | mean=0.64, max=0.80, visit=23, conflicts=24, evidence=0.89, priority=1.28, rel=1.00, pair=0.96, selected=True |
| final-core non-risk | `§312g` §312g Widerrufsrecht | (1) Dem Verbraucher steht bei außerhalb von Geschäftsräumen geschlossenen Verträgen und bei Fernabsatzverträgen ein Widerrufsrecht gemäß § 355 zu.(2) Das Widerrufsrecht besteht, soweit die Parteien nichts anderes vereinbart haben, nicht bei folgenden Verträgen: 1.Verträge zur Lieferung von Waren, die nicht vorgefertigt sind und für deren Herstellung eine individuelle Auswahl oder Bestimmung durch den Verbraucher maßgeblich ... | mean=0.44, max=0.60, visit=26, conflicts=27, evidence=0.58, priority=0.81, rel=0.63, pair=0.96, selected=True |

**诊断。** 风险端点 ['§505', '§491'] 已经进入 local/context 证据，但 final core 在 `score_gap` 处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。

### Case F4. BGB-25 `handoff_invariant` `gpt-4o`

- **Failure mode:** Context Has It, Core Drops It；tags: `context_has_risk_but_core_drops, affected_or_diffuse_region_selected, scored_or_declared_then_outcompeted`。
- **Rollout timeline:** window@`5`, local@`5`, prefix-core@`8`, effective-OC@`40`。
- **Final core:** ['§504', '§506', '§495']；stop=`score_gap`；compression=`88%`；context size=`12`。
- **OC nodes:** ['§504', '§506']；top non-risk distractors: ['§495', '§504', '§491a', '§514']。

| Role | Node | Text snapshot | Injected patch / evidence stats |
|---|---|---|---|
| risk/root-witness | `§505` §505 Geduldete Überziehung | (1) Vereinbart ein Unternehmer in einem Vertrag mit einem Verbraucher über ein laufendes Konto ohne eingeräumte Überziehungsmöglichkeit ein Entgelt für den Fall, dass er eine Überziehung des Kontos duldet, müssen in diesem Vertrag die Angaben nach Artikel 247 § 17 Abs. 1 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche auf einem dauerhaften Datenträger enthalten sein und dem ... | The obligation remains in the ordinary cure class for this reference path, and no surcharge is introduced by this provision. This classification is mandatory for the same obligation path. A contrary downstream treatment would make the same debtor both released from the burden and immediately ...<br><br>`mean=0.44, max=0.60, visit=7, conflicts=10, evidence=0.29, priority=0.44, rel=0.41, pair=0.63, selected=False` |
| risk/root-witness | `§491` §491 Verbraucherdarlehensvertrag | (1) Die Vorschriften dieses Kapitels gelten für Verbraucherdarlehensverträge, soweit nichts anderes bestimmt ist. Verbraucherdarlehensverträge sind Allgemein-Verbraucherdarlehensverträge und Immobiliar-Verbraucherdarlehensverträge.(2) Allgemein-Verbraucherdarlehensverträge sind entgeltliche Darlehensverträge zwischen einem Unternehmer als Darlehensgeber und einem Verbraucher als Darlehensnehmer. Keine Allgemein-Verbraucherdarlehensverträge sind Verträge, 1.bei denen der Nettodarlehensbetrag (Artikel 247 § 3 Abs. 2 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche) weniger als 200 Euro ... | The receiving provision applies the same path only after it has been moved into a surcharge remedy class. This record applies the opposite remedy class immediately on the same obligation path, creating a non-curable enforcement conflict if the upstream classification is still in force.<br><br>`mean=0.49, max=0.80, visit=11, conflicts=18, evidence=0.37, priority=0.52, rel=0.49, pair=0.65, selected=False` |
| affected | `§506` §506 Zahlungsaufschub, sonstige Finanzierungshilfe | (1) Die für Allgemein-Verbraucherdarlehensverträge geltenden Vorschriften der §§ 358 bis 360 und 491a bis 502 sowie 505a bis 505e sind mit Ausnahme des § 492 Abs. 4 und vorbehaltlich der Absätze 3 und 4 auf Verträge entsprechend anzuwenden, durch die ein Unternehmer einem Verbraucher einen entgeltlichen Zahlungsaufschub oder eine sonstige entgeltliche Finanzierungshilfe gewährt. Bezieht sich ... | mean=0.56, max=0.80, visit=12, conflicts=24, evidence=0.62, priority=0.93, rel=0.87, pair=0.65, selected=True |
| affected | `§358` §358 Mit dem widerrufenen Vertrag verbundener Vertrag | (1) Hat der Verbraucher seine auf den Abschluss eines Vertrags über die Lieferung einer Ware oder die Erbringung einer anderen Leistung durch einen Unternehmer gerichtete Willenserklärung wirksam widerrufen, so ist er auch an seine auf den Abschluss eines mit diesem Vertrag verbundenen Darlehensvertrags gerichtete Willenserklärung nicht mehr gebunden.(2) Hat der Verbraucher seine auf den Abschluss ... | mean=0.33, max=0.80, visit=32, conflicts=29, evidence=0.41, priority=0.58, rel=0.54, pair=0.72, selected=False |
| final-core non-risk | `§504` §504 Eingeräumte Überziehungsmöglichkeit | (1) Ist ein Verbraucherdarlehen in der Weise gewährt, dass der Darlehensgeber in einem Vertragsverhältnis über ein laufendes Konto dem Darlehensnehmer das Recht einräumt, sein Konto in bestimmter Höhe zu überziehen (Überziehungsmöglichkeit), hat der Darlehensgeber den Darlehensnehmer in regelmäßigen Zeitabständen über die Angaben zu unterrichten, die sich aus Artikel 247 § 16 des Einführungsgesetzes zum Bürgerlichen ... | mean=0.43, max=0.60, visit=21, conflicts=29, evidence=0.69, priority=1.08, rel=1.00, pair=0.96, selected=True |
| final-core non-risk | `§495` §495 Widerrufsrecht; Bedenkzeit | (1) Dem Darlehensnehmer steht bei einem Verbraucherdarlehensvertrag ein Widerrufsrecht nach § 355 zu.(2) Ein Widerrufsrecht besteht nicht bei Darlehensverträgen, 1.die einen Darlehensvertrag, zu dessen Kündigung der Darlehensgeber wegen Zahlungsverzugs des Darlehensnehmers berechtigt ist, durch Rückzahlungsvereinbarungen ergänzen oder ersetzen, wenn dadurch ein gerichtliches Verfahren vermieden wird und wenn der Gesamtbetrag (Artikel 247 § 3 des Einführungsgesetzes ... | mean=0.34, max=0.70, visit=27, conflicts=61, evidence=0.79, priority=1.02, rel=0.95, pair=0.96, selected=True |

**诊断。** 风险端点 ['§505', '§491'] 已经进入 local/context 证据，但 final core 在 `score_gap` 处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。

### Case F5. BGB-25 `condition_trigger` `deepseek-v3`

- **Failure mode:** Context Has It, Core Drops It；tags: `context_has_risk_but_core_drops, scored_or_declared_then_outcompeted`。
- **Rollout timeline:** window@`1`, local@`1`, prefix-core@`1`, effective-OC@`None`。
- **Final core:** ['§327', '§312']；stop=`below_relative_score`；compression=`92%`；context size=`12`。
- **OC nodes:** -；top non-risk distractors: ['§327', '§312', '§312f', '§495']。

| Role | Node | Text snapshot | Injected patch / evidence stats |
|---|---|---|---|
| risk/root-witness | `§505` §505 Geduldete Überziehung | (1) Vereinbart ein Unternehmer in einem Vertrag mit einem Verbraucher über ein laufendes Konto ohne eingeräumte Überziehungsmöglichkeit ein Entgelt für den Fall, dass er eine Überziehung des Kontos duldet, müssen in diesem Vertrag die Angaben nach Artikel 247 § 17 Abs. 1 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche auf einem dauerhaften Datenträger enthalten sein und dem ... | A supplementary payment becomes due only after formal notice has been served and the cure period has expired. This record states that notice is still pending. This classification is mandatory for the same obligation path. A contrary downstream treatment would make the same debtor both ...<br><br>`mean=0.42, max=0.80, visit=6, conflicts=5, evidence=0.22, priority=0.36, rel=0.34, pair=0.60, selected=False` |
| risk/root-witness | `§491` §491 Verbraucherdarlehensvertrag | (1) Die Vorschriften dieses Kapitels gelten für Verbraucherdarlehensverträge, soweit nichts anderes bestimmt ist. Verbraucherdarlehensverträge sind Allgemein-Verbraucherdarlehensverträge und Immobiliar-Verbraucherdarlehensverträge.(2) Allgemein-Verbraucherdarlehensverträge sind entgeltliche Darlehensverträge zwischen einem Unternehmer als Darlehensgeber und einem Verbraucher als Darlehensnehmer. Keine Allgemein-Verbraucherdarlehensverträge sind Verträge, 1.bei denen der Nettodarlehensbetrag (Artikel 247 § 3 Abs. 2 des Einführungsgesetzes zum Bürgerlichen Gesetzbuche) weniger als 200 Euro ... | The downstream remedy applies the supplementary payment immediately on the same obligation path. This record applies the opposite remedy class immediately on the same obligation path, creating a non-curable enforcement conflict if the upstream classification is still in force.<br><br>`mean=0.41, max=0.70, visit=8, conflicts=9, evidence=0.33, priority=0.49, rel=0.46, pair=0.66, selected=False` |
| affected | `§506` §506 Zahlungsaufschub, sonstige Finanzierungshilfe | (1) Die für Allgemein-Verbraucherdarlehensverträge geltenden Vorschriften der §§ 358 bis 360 und 491a bis 502 sowie 505a bis 505e sind mit Ausnahme des § 492 Abs. 4 und vorbehaltlich der Absätze 3 und 4 auf Verträge entsprechend anzuwenden, durch die ein Unternehmer einem Verbraucher einen entgeltlichen Zahlungsaufschub oder eine sonstige entgeltliche Finanzierungshilfe gewährt. Bezieht sich ... | mean=0.54, max=0.70, visit=10, conflicts=10, evidence=0.49, priority=0.65, rel=0.61, pair=0.66, selected=True |
| affected | `§358` §358 Mit dem widerrufenen Vertrag verbundener Vertrag | (1) Hat der Verbraucher seine auf den Abschluss eines Vertrags über die Lieferung einer Ware oder die Erbringung einer anderen Leistung durch einen Unternehmer gerichtete Willenserklärung wirksam widerrufen, so ist er auch an seine auf den Abschluss eines mit diesem Vertrag verbundenen Darlehensvertrags gerichtete Willenserklärung nicht mehr gebunden.(2) Hat der Verbraucher seine auf den Abschluss ... | mean=0.42, max=0.60, visit=12, conflicts=8, evidence=0.30, priority=0.44, rel=0.41, pair=0.55, selected=False |
| final-core non-risk | `§327` §327 Anwendungsbereich | (1) Die Vorschriften dieses Untertitels sind auf Verbraucherverträge anzuwenden, welche die Bereitstellung digitaler Inhalte oder digitaler Dienstleistungen (digitale Produkte) durch den Unternehmer gegen Zahlung eines Preises zum Gegenstand haben. Preis im Sinne dieses Untertitels ist auch eine digitale Darstellung eines Werts.(2) Digitale Inhalte sind Daten, die in digitaler Form erstellt und bereitgestellt werden. Digitale Dienstleistungen ... | mean=0.41, max=0.70, visit=27, conflicts=33, evidence=0.87, priority=1.07, rel=1.00, pair=0.83, selected=True |
| final-core non-risk | `§312` §312 Anwendungsbereich | (1) Die Vorschriften der Kapitel 1 und 2 dieses Untertitels sind auf Verbraucherverträge anzuwenden, bei denen sich der Verbraucher zu der Zahlung eines Preises verpflichtet.(1a) Die Vorschriften der Kapitel 1 und 2 dieses Untertitels sind auch auf Verbraucherverträge anzuwenden, bei denen der Verbraucher dem Unternehmer personenbezogene Daten bereitstellt oder sich hierzu verpflichtet. Dies gilt nicht, ... | mean=0.37, max=0.80, visit=22, conflicts=18, evidence=0.48, priority=0.68, rel=0.64, pair=0.83, selected=True |

**诊断。** 风险端点 ['§505', '§491'] 已经进入 local/context 证据，但 final core 在 `below_relative_score` 处提前压缩，优先保留了更高频或 OC 更强的非注入节点；这是 evidence retention 问题，不是完全未发现。

## 3. risk-all 失败是否真失败

长环 critical 中，`risk-any=True` 但 `risk-all=False` 的 partial case 有 `11` 个。其中 `5` 个同时保留 affected 节点，说明不少 case 的最终子图落在风险扩散区。这支持一个更稳的论文口径：`risk-all` 是严格上界指标，不应作为唯一主指标；`risk-any + affected/valuable retention + effective OC + compression` 更符合结构性缺陷的修复语义。

## 4. 算法改进方向

1. **Core retention 应该利用“曾经进入 context/local 的风险证据”。** 现在 final core 会因为 `score_gap` 或相对优先级阈值过早剪掉曾经被多次看到的风险节点。
2. **OC 需要从 node bonus 升级为 pair/path proof。** 许多失败 case 的 OC 落在原生高风险节点上，挤压了注入端点；应把 OC 与 root/witness/affected 的路径关系一起计入。
3. **风险扩散区要成为正式指标。** 如果 affected 节点被保留，不能简单算作完全失败；这代表算法定位到了可修复入口或下游冲击区。
4. **final core 不应只追最强局部异常。** CUAD 中原生合同噪声节点经常有更高 conflict count；core 选择需要保留“结构冲突解释链”的最小覆盖，而不只是最高频冲突节点。

## 5. 对论文指标的建议

- 主指标：`Root@3 + Risk-any + Effective OC + Compression`。
- 辅助指标：`Risk-all`，明确标注为 strict endpoint-retention upper bound。
- 新增解释指标：`Context-to-core retention`，即 risk 节点进入 context 后最终是否被 core 保留。
- 对 CUAD：强调高噪声合同图中 SA 能找到风险扩散区，但原生合同噪声会影响 full endpoint retention。
- 对 BGB：强调 clean legal graph 上长环导致 one-shot root 定位失败，而 SA 通过 rollout 能恢复部分 root/OC 证据。

## 6. Rebuild warnings

- 无。所有审计 case 都成功重建注入后的 SCC 现场。
