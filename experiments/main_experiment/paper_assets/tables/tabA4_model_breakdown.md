# Table A4. Model-level Breakdown

| model | method | n | zero_valid_cases | root_at_3 | risk_any | risk_all | compression |
|---|---|---|---|---|---|---|---|
| gpt-4o | oracle-risk Naive | 80 | 6 | 37% | 76% | 37% | 65% |
| gpt-4o | sa-mcgs | 80 | 0 | 86% | 100% | 75% | 51% |
| deepseek-v3 | oracle-risk Naive | 80 | 0 | 87% | 95% | 87% | 74% |
| deepseek-v3 | sa-mcgs | 80 | 0 | 80% | 95% | 76% | 51% |
| qwen2.5-72b | oracle-risk Naive | 80 | 40 | 11% | 48% | 28% | 22% |
| qwen2.5-72b | sa-mcgs | 80 | 0 | 70% | 98% | 75% | 53% |
| gemini-2.5-pro | oracle-risk Naive | 80 | 0 | 99% | 100% | 97% | 79% |
| gemini-2.5-pro | sa-mcgs | 80 | 0 | 88% | 98% | 84% | 56% |
