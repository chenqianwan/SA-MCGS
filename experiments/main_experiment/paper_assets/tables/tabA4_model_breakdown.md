# Table A4. Model-level Breakdown

| model | method | n | errors | root_at_3 | risk_any | risk_all | compression | effective_compression |
|---|---|---|---|---|---|---|---|---|
| gpt-4o | naive | 80 | 17 | 26% | 55% | 15% | 68% | 66% |
| gpt-4o | sa-mcgs | 80 | 0 | 86% | 100% | 75% | 51% | 51% |
| deepseek-v3 | naive | 80 | 0 | 75% | 88% | 74% | 70% | 70% |
| deepseek-v3 | sa-mcgs | 80 | 0 | 80% | 95% | 76% | 51% | 51% |
| qwen2.5-72b | naive | 80 | 41 | 2% | 46% | 14% | 43% | 41% |
| qwen2.5-72b | sa-mcgs | 80 | 0 | 70% | 98% | 75% | 53% | 53% |
| gemini-2.5-pro | naive | 80 | 1 | 90% | 98% | 85% | 75% | 75% |
| gemini-2.5-pro | sa-mcgs | 80 | 0 | 88% | 98% | 84% | 56% | 56% |
