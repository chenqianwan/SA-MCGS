# Gemini 2.5 new-citation audit

Audit time: 2026-10-01T14:00:48Z. Scope: `comanici2025gemini25` and its model-identification use in §4.4, `paper/latex/acl_latex.tex:324`. This subtask made no manuscript or bibliography-style edits. The original bibliography entry is saved locally in `original_entry.bib`; raw primary-source snapshots and machine-readable evidence accompany this report.

## Decision

Keep this source. It is the correct primary technical report for Gemini 2.5 Pro. Its title, year, arXiv identifier, and DOI are correct. Replace the imported 3,435-name author field with the report’s actual group byline, `author = {{Gemini Team}}`, preserve the title and 2025, and pin the source to v6 with a visible version note. This is a bibliographic repair, not a change of model or a replacement with another paper.

The existing list matches arXiv’s machine-readable author metadata **exactly, in both text and order**. Its broken names therefore should not be characterized as invented by the prior editor. The defect originates upstream: the full paper lists 3,424 contributors, while machine metadata splits 11 people’s names into 22 entries and loses the parenthesized aliases.

## Field-by-field verification

| Field | Original | Primary evidence | Verdict |
|---|---|---|---|
| Title | Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities | arXiv title, DataCite title, PDF p. 1 | Correct. The PDF terminal period need not be stored in BibTeX. Preserve protected model capitalization. |
| Year | 2025 | arXiv first submission, all revisions, DataCite publicationYear, PDF copyright | Correct. Do not change to 2026 because of audit/access date. |
| arXiv ID | 2507.06261 | arXiv and DataCite | Correct. |
| DOI | 10.48550/arXiv.2507.06261 | arXiv’s explicit arXiv-issued DOI link; DataCite exact DOI lookup succeeds | Correct repository DOI, not a journal-publication DOI. DataCite lowercase `arxiv` spelling is equivalent. |
| URL | unversioned arXiv abstract | currently resolves to v6 | Valid; use v6 URL and a version note for reproducible source identification. |
| Author | 3,435 comma-formatted names | exact match to all arXiv citation_author tags; first authors Comanici, Bieber, Schaekermann | Faithful metadata import but malformed relative to primary report, and unwieldy. |
| Actual report byline | not represented as such | arXiv HTML title page and visually inspected v6 PDF p. 1: “Gemini Team, Google”; official Google-hosted report has same byline | Use the collective author `{Gemini Team}`. Google identifies the organization; do not invent `Google DeepMind` as replacement author from the logo. |
| Type/venue | article, arXiv preprint | DataCite says Preprint, publisher arXiv, BibTeX mapping misc | Existing article-with-preprint-journal convention is defensible; misc is semantically cleaner. Neither should claim a peer-reviewed venue. |

Primary links: [arXiv record](https://arxiv.org/abs/2507.06261), [versioned full text](https://arxiv.org/html/2507.06261v6), [versioned PDF](https://arxiv.org/pdf/2507.06261v6), [DataCite registration](https://api.datacite.org/dois/10.48550/arXiv.2507.06261), [Google-hosted PDF](https://storage.googleapis.com/deepmind-media/gemini/gemini_v2_5_report.pdf).

## Versions and publication status

The current primary record is v6, dated 19 December 2025. The version history is: v1 7 July 2025; v2 11 July; v3 17 July; v4 22 July; v5 16 October; v6 19 December. Exact UTC timestamps are in `evidence.json`.

The arXiv page has no journal-reference field; the Atom record has neither a journal reference nor a publisher DOI; DataCite identifies a Preprint and has no related published-version identifier. Exact-title and official Google-site searches did not identify a formal publisher version. The evidence supports continuing to cite an arXiv technical report. This audit does not claim to prove that no formal publication exists anywhere.

The DOI is version-independent. With the current ACL style the DOI wins over the URL for the clickable title, so a pinned URL field alone does not make the rendered reference visibly version-specific. Add a note such as `Version 6, 19 December 2025` if pinning is desired. Do not append `v6` to the registered DOI.

## Full author audit, not a spot check

The comparison included all 3,435 author fields, not only the beginning of the list. `author_comparison.json` records exact equality and no local-versus-arXiv differences. `metadata_vs_fulltext_differences.json` records all differences from the 3,424 primary full-text contributor lines, preserving positions on both sides.

All 11 substantive splitting defects occur where the original full name contains a parenthesized alias:

| Positions in imported list, one-based | Imported as separate people | Full paper, §7 |
|---|---|---|
| 274–275 | Jerry / Liu | Jerry (Chun-Ting) Liu |
| 395–396 | Xintian / Wu | Xintian (Cindy) Wu |
| 882–883 | Qiong / Hu | Qiong (Q) Hu |
| 962–963 | Chuqiao / Xu | Chuqiao (Joyce) Xu |
| 1693–1694 | Jilei / Wang | Jilei (Jerry) Wang |
| 1948–1949 | Katrina / Xu | Katrina (Xinyi) Xu |
| 2025–2026 | Tony / Nguyên | Tony (Tuấn) Nguyễn |
| 2393–2394 | Zhixin / Lai | Zhixin (Lucas) Lai |
| 2464–2465 | Hui / Li | Hui (Elena) Li |
| 2551–2552 | Warren / Chen | Warren (Weilun) Chen |
| 3234–3235 | Yuvein / Zhu | Yuvein (Yonghao) Zhu |

The remaining eight comparison differences comprise seven straight/curly apostrophe typography changes and `Marcáurelio Ranzato` versus the full text’s `Marc’aurelio Ranzato`. Tony’s surname additionally loses a Vietnamese diacritic in machine metadata. These are reasons to avoid blindly trusting the giant metadata export; they are not grounds to guess or silently normalize thousands of people’s names.

A complete person-author repair could reconstruct names from §7, preserve order, combine aliases correctly, and validate compound surnames and Unicode/TeX handling. It would still produce a needlessly huge author database. The paper already supplies an explicit collective byline, so using it is the strongest small repair. The bib key can remain `comanici2025gemini25`; internal keys need not match the displayed author.

## What the citation supports in §4.4

1. **Gemini 2.5 Pro model identity: direct support.** The abstract and introduction explicitly include this model. More decisively, §3.1 Table 2 maps “Gemini 2.5 Pro” to the exact AI Studio ID `gemini-2.5-pro`. This avoids conflating Pro with Flash, Flash-Lite, or Deep Think. [Table 2](https://arxiv.org/html/2507.06261v6#S3.T2)
2. **Stable public API name: direct official corroboration.** The official model page lists `gemini-2.5-pro`, stable, latest model update June 2025. The 17 June 2025 developer announcement says Pro became stable and generally available and identifies the stable string; at that release it matched the 06-05 preview. [Model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro), [release announcement](https://developers.googleblog.com/en/gemini-2-5-thinking-model-updates/)
3. **“Proprietary”: correct classification, but the report is not explicit license evidence.** Full-text searches found no proprietary label or weights-release license statement. The report’s API-based evaluation is consistent with the classification but does not logically prove it. Google’s own Gemma model card explicitly refers to its “proprietary Gemini models”; this is family-level official corroboration. Retaining the label is supported, but do not claim the cited report explicitly states it. There is no need to burden §4.4 with an unrelated Gemma citation merely to defend routine model categorization. [Official corroboration, Ethics and Safety](https://ai.google.dev/gemma/docs/core/model_card_4#ethics_and_safety)
4. **Actual experiment deployment: not proven by a citation.** The source identifies what `gemini-2.5-pro` denotes. The authors’ run records must establish which endpoint/provider was actually called, on what dates, with what thinking/sampling settings. Do not infer a dated snapshot from a stable alias unless the experiment records support it.
5. **Graph-retention and SA-MCGS performance: outside this source’s role.** The citation is attached to the backbone name, not to the manuscript’s comparative results. No Google benchmark number should be used as evidence for the paper’s own legal/dependency-graph claims.

## Exact bibliography-style consequences

An isolated Tectonic build was run with the repository’s unchanged `acl_natbib.bst`, testing the original list, the actual collective byline, and the common shortened-person-list alternative. The source and all compilation products are in this audit directory.

- Original full list prints the first **19** authors followed by **“and 3416 others”**. The ACL style already truncates display; it does not literally print all 3,435 names. The author database and natbib optional long-name metadata remain very large. The count is also 11 too high relative to §7.
- `Comanici, Gheorghe and Bieber, Eric and Schaekermann, Mike and others` prints **“and 1 others”** under this particular style. Do not use this otherwise common BibTeX abbreviation without changing style behavior. This task does not require a style change.
- `{Gemini Team}` prints **“Gemini Team. 2025.”**, compiles cleanly, and protects the collective name against personal-name parsing.
- The isolated test produced one PDF page, no BibTeX warnings, and no TeX warning/overfull/missing-character messages. It is a targeted bibliography test, not a full-paper layout certification.
- At the time inspected, `paper/latex/acl_latex.bbl` lacked this new entry entirely. The existing generated file was stale and could not be used to judge the revised bibliography; the parent task should rebuild the actual manuscript after applying corrections.

## Recommended concrete entry

This preserves the project’s existing arXiv-entry convention and changes only attribution and version specificity:

```bibtex
@article{comanici2025gemini25,
    author  = {{Gemini Team}},
    title   = {{Gemini 2.5}: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities},
    journal = {arXiv preprint arXiv:2507.06261},
    year    = {2025},
    doi     = {10.48550/arXiv.2507.06261},
    url     = {https://arxiv.org/abs/2507.06261v6},
    note    = {Version 6, 19 December 2025},
}
```

If the parent task standardizes preprints as `@misc`, use the same author/title/year/DOI/URL/note plus `eprint = {2507.06261}`, `archivePrefix = {arXiv}`, `primaryClass = {cs.CL}`, and a visible `howpublished = {arXiv preprint arXiv:2507.06261}`. Merely storing arXiv-specific fields does not guarantee that an older `.bst` renders them; inspect the result. Do not claim a journal, conference, volume, or pages not present in a primary record.

## Severity and limitations

**P2, repair before submission:** malformed upstream author metadata and inaccurate remaining-author count; the collective byline resolves these without modifying `acl_natbib.bst`. **No substantive citation mismatch:** this is the correct Gemini 2.5 Pro report. **Minor reproducibility improvement:** pin v6 in URL and note. **Evidence boundary:** the report supports model identity, while provider documentation supports routine proprietary classification; neither replaces actual execution provenance.

The arXiv BibTeX endpoint returned HTTP 406, and the web DOI opener failed. These did not prevent verification: the official HTML metadata, Atom API, full report, and DataCite registration were retrieved independently. The Google PDF screenshot endpoint failed; the downloaded arXiv v6 first page was rendered locally and visually inspected instead. Raw-source snapshots and SHA-256 hashes are listed in `evidence.json`.
