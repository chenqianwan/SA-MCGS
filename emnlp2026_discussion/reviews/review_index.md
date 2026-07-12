# Review Index

Submission: 8229

## Reviewer Files

- [Reviewer iMEC](reviewer_iMEC.md)
- [Reviewer rxvy](reviewer_rxvy.md)
- [Reviewer wWUk](reviewer_wWUk.md)

## Archived Screenshots

- `images/reviewer_iMEC.png`
- `images/reviewer_rxvy_part1.png`
- `images/reviewer_rxvy_part2.png`
- `images/reviewer_wWUk_part1.png`
- `images/reviewer_wWUk_part2.png`

## Ratings

| Reviewer | Overall Assessment | Soundness | Excitement | Confidence | Reproducibility | Datasets | Software |
|---|---:|---:|---:|---:|---:|---:|---:|
| iMEC | 2.5 = Borderline Findings | 3 | 3 | 3 | 3 | 1 | 1 |
| rxvy | 2.5 = Borderline Findings | 2.5 | 3.5 | 4 | 3 | 3 | 3 |
| wWUk | 3 = Findings | 3.5 | 3 | 3 | 4 | 4 | 4 |

## Recurring Concerns

1. Component-level ablations for SA-MCGS modules are insufficient.
2. Practical inference cost needs token/call/runtime characterization.
3. Baselines may be narrow or unfairly shaped by prompt decomposition/output reliability.
4. Evaluation relies primarily on injected risks; naturally occurring or negative cases would strengthen claims.
5. SA-MCGS is not uniformly better across all models, especially Gemini 2.5 Pro and DeepSeek-V3.
6. Need clearer reporting of subgraph cleanliness, e.g. precision or irrelevant-node rate.
7. Need sensitivity analysis for fixed prior coefficients.
8. Need careful framing for high-stakes use as decision support, not automated adjudication.

