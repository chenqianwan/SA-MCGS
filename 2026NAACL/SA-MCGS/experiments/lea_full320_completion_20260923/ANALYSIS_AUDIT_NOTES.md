# Independent audit: three completed models

Three complete models, 80 variants each; Qwen excluded
Source SHA256: 03da5ae700189797d127f7e924995e455755f684f04d575711b6a49c355f85f9

All figures below are matched case counts. Full = Full-SCC; comp = mean fraction removed.

| Model | Group | N / physical SCCs | Root Full / LEA | Risk-all Full / LEA | Risk-any Full / LEA | Comp Full / LEA |
|---|---|---:|---:|---:|---:|---:|
| gpt-4o | overall:all | 80 / 20 | 69/80 / 63/80 | 60/80 / 35/80 | 80/80 / 77/80 | 51.26% / 51.26% |
| gpt-4o | domain:bgb | 12 / 3 | 8/12 / 5/12 | 7/12 / 0/12 | 12/12 / 10/12 | 50.33% / 50.33% |
| gpt-4o | domain:cuad | 40 / 10 | 33/40 / 32/40 | 29/40 / 18/40 | 40/40 / 39/40 | 52.06% / 52.06% |
| gpt-4o | domain:debian | 8 / 2 | 8/8 / 6/8 | 8/8 / 6/8 | 8/8 / 8/8 | 52.27% / 52.27% |
| gpt-4o | domain:sec_ex21 | 20 / 5 | 20/20 / 20/20 | 16/20 / 11/20 | 20/20 / 20/20 | 49.80% / 49.80% |
| gpt-4o | scale:large | 20 / 5 | 15/20 / 15/20 | 12/20 / 5/20 | 20/20 / 20/20 | 52.94% / 52.94% |
| gpt-4o | scale:medium | 24 / 6 | 20/24 / 18/24 | 18/24 / 9/24 | 24/24 / 23/24 | 51.32% / 51.32% |
| gpt-4o | scale:small | 36 / 9 | 34/36 / 30/36 | 30/36 / 21/36 | 36/36 / 34/36 | 50.28% / 50.28% |
| gemini-2.5-pro | overall:all | 80 / 20 | 70/80 / 70/80 | 67/80 / 67/80 | 78/80 / 80/80 | 55.86% / 51.26% |
| gemini-2.5-pro | domain:bgb | 12 / 3 | 12/12 / 12/12 | 11/12 / 12/12 | 12/12 / 12/12 | 58.09% / 50.33% |
| gemini-2.5-pro | domain:cuad | 40 / 10 | 33/40 / 33/40 | 32/40 / 34/40 | 38/40 / 40/40 | 57.93% / 52.06% |
| gemini-2.5-pro | domain:debian | 8 / 2 | 7/8 / 6/8 | 7/8 / 7/8 | 8/8 / 8/8 | 54.36% / 52.27% |
| gemini-2.5-pro | domain:sec_ex21 | 20 / 5 | 18/20 / 19/20 | 17/20 / 14/20 | 20/20 / 20/20 | 50.98% / 49.80% |
| gemini-2.5-pro | scale:large | 20 / 5 | 16/20 / 19/20 | 17/20 / 17/20 | 19/20 / 20/20 | 68.20% / 52.94% |
| gemini-2.5-pro | scale:medium | 24 / 6 | 20/24 / 17/24 | 18/24 / 18/24 | 23/24 / 24/24 | 51.76% / 51.32% |
| gemini-2.5-pro | scale:small | 36 / 9 | 34/36 / 34/36 | 32/36 / 32/36 | 36/36 / 36/36 | 51.73% / 50.28% |
| deepseek-v3 | overall:all | 80 / 20 | 64/80 / 63/80 | 61/80 / 61/80 | 76/80 / 80/80 | 51.26% / 51.26% |
| deepseek-v3 | domain:bgb | 12 / 3 | 11/12 / 5/12 | 7/12 / 6/12 | 11/12 / 12/12 | 50.33% / 50.33% |
| deepseek-v3 | domain:cuad | 40 / 10 | 25/40 / 31/40 | 26/40 / 27/40 | 37/40 / 40/40 | 52.06% / 52.06% |
| deepseek-v3 | domain:debian | 8 / 2 | 8/8 / 7/8 | 8/8 / 8/8 | 8/8 / 8/8 | 52.27% / 52.27% |
| deepseek-v3 | domain:sec_ex21 | 20 / 5 | 20/20 / 20/20 | 20/20 / 20/20 | 20/20 / 20/20 | 49.80% / 49.80% |
| deepseek-v3 | scale:large | 20 / 5 | 14/20 / 17/20 | 10/20 / 13/20 | 17/20 / 20/20 | 52.94% / 52.94% |
| deepseek-v3 | scale:medium | 24 / 6 | 15/24 / 17/24 | 19/24 / 17/24 | 24/24 / 24/24 | 51.32% / 51.32% |
| deepseek-v3 | scale:small | 36 / 9 | 35/36 / 29/36 | 32/36 / 31/36 | 35/36 / 36/36 | 50.28% / 50.28% |

Interpretation and boundaries:

- Full-SCC = sa-mcgs deployable core_evidence_risk_subgraph_nodes, not legacy risk_subgraph_nodes.
- No p-values: each model has 80 variants from 20 physical SCCs (four templates per SCC); models also share cases.
- Root@3 means injected root in final top three. Risk-any/all means some/all frozen injected risk nodes retained. Compression is one minus selected nodes divided by SCC nodes.
- Strict invalid outputs score zero for detection and null for compression. Full-SCC/LEA invalid counts are all zero; one-shot invalid counts GPT 17, Gemini 1, DeepSeek 0.
- GPT: Full-SCC Risk-all is better in all four domains and all three size groups, with identical selected-node counts in all 80 pairs. Paired wins 32 versus 7.
- Gemini: Root@3 and Risk-all tie overall. Full-SCC compression +4.60 pp, concentrated in large cases (+15.26 pp), but large Root@3 is 16/20 versus LEA 19/20. Not lossless or universal dominance.
- DeepSeek: Risk-all ties, Root@3 differs by one case. BGB favors Full-SCC (11/12 versus 5/12 roots), CUAD favors LEA (25/40 versus 31/40 roots). LEA wins both Root@3 and Risk-all by 3/20 on large cases.
- Gemini one-shot has Root@3 72/80 and Risk-all 68/80 versus 70/80 and 67/80 for both graph methods; valid-output compression 74.98%, one strict invalid retained. Do not claim graph methods universally beat one-shot.
- No historical one-shot/Full-SCC token data here, so no comparative dollar/token-efficiency claim. Incremental completion spend is not total historical method cost.
- The user confirmed with XHub that historical Qwen also used AWQ. Backend differs; exact historical checkpoint revision and server defaults remain unverified. Do not claim a known precision change.

Qwen raw-output follow-up (details in ANALYSIS_QWEN_AUDIT_NOTES.json):

- All 80 Qwen cases matched frozen identity and manual metric recomputation. Full-SCC versus LEA: Root@3 56/80 versus 54/80; Risk-all 60/80 versus 35/80; Risk-any both 78/80; compression 52.82% versus 51.26%.
- Qwen has 34/80 cases with 101 exhausted JSON windows, all in CUAD. Under the frozen historical three-attempt rule these return an empty dict and fallback; retain cases in the primary denominator.
- Qwen 1268 logical non-TT evaluations consumed 1695 API calls (427 retries); 529 calls hit the 2048-token cap, 528 in CUAD and one in SEC. Length termination is not identical to final parse failure.
- Exhaustion is zero for all new GPT6, Gemini7 and DeepSeek80 cases. Historical GPT74/Gemini73 lack the diagnostic field, so quality is unknown there.
- Qwen results measure the complete method under the fixed output budget and fallback protocol; the gap cannot be attributed exclusively to search quality. Outside CUAD, neither method comparison group has LEA exhaustion, yet Risk-all is Full 27/40 versus LEA15/40; this is descriptive and not a causal separation.
