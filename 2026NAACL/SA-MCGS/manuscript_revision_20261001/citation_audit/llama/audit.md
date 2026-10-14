# Audit of `grattafiori2024llama3`

Audited 2026-10-01. This audit did not modify the manuscript or `paper/latex/custom.bib`.

## Verdict

**The source is genuine and directly supports the manuscript’s identification of Llama 3.1-8B-Instruct as an open-weight backbone.** The title, 2024 year, arXiv identifier, DOI, and existing URL are correct. The large local author field reproduces upstream arXiv metadata exactly, including two clear split-name defects. The source itself also repeats two names; these duplicates must not be described as errors introduced by the manuscript.

The preferred group-author option is `author = {{Llama Team}}`, grounded in both the report’s main byline and Meta’s official publication page. A repaired full-author option is also supplied. Both preserve the existing citation key and pin the URL to v3.

## Manuscript purpose and source reading

The citation appears at `paper/latex/acl_latex.tex:324`, in the five-backbone comparison paragraph. It identifies a model, not an external performance result or a claim about the proposed method.

The report’s introduction and Table 1 identify the 3.1 generation and distinguish its 8B instruction-tuned variant from both the base model and the April 2024 Llama 3 release. The report explains that its shorter title/name covers the 3.1 models. The release discussion supports the open-weight characterization. The current wording therefore does **not** require a different paper merely because its title says Llama 3. [Report, introduction and Table 1](https://arxiv.org/html/2407.21783v3#S1).

The official Meta model card independently confirms the family, 8B size, instruction-tuned status, July 23, 2024 release, and checkpoint use/download instructions. The legacy URL with `Meta-Llama-` redirects to the current `Llama-` repository URL; the card’s usage example retains the legacy identifier. This is an official repository alias, not evidence of a different checkpoint. [Official model card](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct), [Meta’s GitHub model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md).

Primary sections read: introduction/Table 1; general overview; opening post-training/modeling discussion; §9.1 discussion of open weights; v1 and v3 contributor appendices; official model-card identity, intended-use, release, and usage sections. The citation establishes the model’s identity and properties. Whether the experiments actually used that checkpoint is a separate question for local run configuration and logs.

## Bibliographic fields

| Field | Result |
|---|---|
| Title | Correct: The Llama 3 Herd of Models. |
| Year | Correct: 2024. Meta’s report date is July 23; first arXiv submission July 31; v3 submission November 23. |
| Venue | Correctly labeled an arXiv preprint. No verified formal journal or conference venue found. |
| DOI | Correct: `10.48550/arXiv.2407.21783`; direct resolver returned HTTP 200 and the expected arXiv record. |
| URL | Existing canonical URL works. Pin `/abs/2407.21783v3` to stabilize the selected author version. |
| Entry type | Existing `@article` plus explicit arXiv-preprint journal is defensible; official arXiv export uses `@misc`. No forced type change is necessary. |

Meta explicitly names arXiv as publisher. DataCite registers this DOI as a preprint, publication year 2024, version 3, with no related formal-publication identifier. The arXiv page gives no journal reference. Targeted exact-title venue searches did not find a formal publication; the official NeurIPS 2024 proceedings index contains no matching title. Do not relabel this reference as NeurIPS. This is a bounded verification, not a proof that no later publication can exist. [Meta publication record](https://ai.meta.com/research/publications/the-llama-3-herd-of-models/), [DOI registration](https://api.datacite.org/dois/10.48550/arXiv.2407.21783), [official NeurIPS 2024 index](https://proceedings.neurips.cc/paper_files/paper/2024).

## Why Grattafiori versus Dubey

**Grattafiori-first is valid for v3; Dubey-first is valid for v1/v2.** The contributor appendix groups core contributors before contributors, ordering each group by given name. Aaron Grattafiori appears in the contributors group in v1 and the core group in v3, which explains the lead-name change without inventing a new paper or new publication year. The current key and Grattafiori author-year attribution are not fabricated. [v1 metadata](https://arxiv.org/abs/2407.21783v1), [v2 metadata](https://arxiv.org/abs/2407.21783v2), [v3 metadata](https://arxiv.org/abs/2407.21783v3), [v3 contributor appendix](https://arxiv.org/html/2407.21783v3#Sx1).

## Exhaustive author-string comparison

The current local field has **561 BibTeX name tokens** and exactly matches all 561 `citation_author` meta tags in arXiv v3. The fulltext appendix instead has **559 listed entries**, comprising 236 core entries and 323 contributor entries; 557 name strings are distinct. Reconstructing the local `Family, Given` strings into display-name order and comparing the complete sequences found exactly two discrepancies:

| Current fragment | Verified replacement | Fulltext location |
|---|---|---|
| `and Guangyi and Zhang and` | `and Zhang, Guangyi (Jack) and` | Contributors: after Grigory Sizov, before Guna Lakshminarayanan; fulltext position 340. |
| `and Yu and Wang and` | `and Wang, Yu (Sid) and` | Contributors: after Youngjin Nam, before Yu Zhao; fulltext position 547. |

These repairs recover single people whose parenthesized aliases were lost by metadata parsing. The complete repaired 559-entry list matches the fulltext **exactly in display-name order**. [Primary appendix for both repairs](https://arxiv.org/html/2407.21783v3#Sx1.SSx2).

The fulltext itself repeats Shaun Lindsay at positions 482–483 and Shuqiang Zhang at positions 489–490. These are upstream repetitions, not additional locally invented names. The supplied full-author variant retains them to avoid silently editing published contributor attribution. We have not established whether the identical strings denote one or more people. Compound-surname partitioning otherwise follows official metadata; this audit does not claim separate biographical identity verification of hundreds of people.

## Recommended group-author attribution

The report’s main byline is **Llama Team, AI @ Meta**, and Meta’s own publication page identifies **Llama team** as its author. `author = {{Llama Team}}` therefore uses a published primary-source byline, rather than substituting an unsupported corporate author. It is a clean option if model-report citations are being standardized to teams/institutions. [Report byline](https://arxiv.org/html/2407.21783v3), [Meta author field](https://ai.meta.com/research/publications/the-llama-3-herd-of-models/).

Use `recommended_group_author_v3.bib` for that option. Use `corrected_full_entry_v3.bib` if preserving the v3 personal-author attribution. The latter changes only the two split names and the version-pinned URL. Keeping the internal key `grattafiori2024llama3` is harmless in either option; the rendered author comes from the author field.

## Evidence files

- `evidence.json`: field-by-field decisions, claim support, versions, counts, scope, limitations, and source URLs.
- `changes.json`: exact old/new replacements and primary-source locations for the repaired full-author variant.
- `recommended_group_author_v3.bib`: recommended source-grounded team attribution.
- `corrected_full_entry_v3.bib`: exact full-list repair, retaining upstream duplicates.
- `original_entry.bib`: audited manuscript entry before any root-agent edits.
- `arxiv_authors_v1.json`, `arxiv_authors_v2.json`, `arxiv_authors_v3.json`: parsed primary metadata.
- `fulltext_authors_v1.json`, `fulltext_authors_v3.json`: complete appendix lists.
- Saved official HTML, fulltext, DOI JSON, model-card HTML, official GitHub card, and retrieval logs preserve the evidence.

The Hugging Face raw README endpoint returned HTTP 401; the public model-card HTML and Meta’s public GitHub card were successfully read. No gated weights or private contents were accessed.
