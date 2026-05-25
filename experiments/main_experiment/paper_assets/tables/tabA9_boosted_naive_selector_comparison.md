# Table A9. Boosted Naive Selector Comparison

| control | n | root_at_3 | risk_any | risk_all | compression | role |
|---|---|---|---|---|---|---|
| one-shot Naive | 320 | 48% | 72% | 47% | 67% | original locked control |
| boosted Naive single-attempt mean | 320 cases / 3200 attempts | 47% | 67% | 48% | 50% | raw repeated-sampling mean |
| boosted Naive self_top3 | 320 | 52% | 75% | 52% | 60% | non-oracle selector |
| boosted Naive oracle_risk_top3 | 320 | 58% | 79% | 62% | 60% | main oracle-risk baseline |
| boosted Naive oracle_compression_top3 | 320 | 53% | 75% | 47% | 63% | compression-first diagnostic |
| SA-MCGS | 320 | 81% | 98% | 78% | 53% | proposed method |
