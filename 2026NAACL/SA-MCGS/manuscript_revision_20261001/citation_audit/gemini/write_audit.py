from pathlib import Path
import json, re, hashlib
from bs4 import BeautifulSoup
p=Path(__file__).resolve().parent
access='2026-10-01T14:00:48Z'
comparison=json.loads((p/'author_comparison.json').read_text())
diffs=json.loads((p/'metadata_vs_fulltext_differences.json').read_text())
contributors=json.loads((p/'fulltext_contributors.json').read_text())
sources=[
 {'id':'arxiv_abs','url':'https://arxiv.org/abs/2507.06261','accessed_utc':access,'version':'v6, revised 2025-12-19','saved_file':'arxiv_abs.html','locations':['h1.title','meta[name=citation_author]','Submission history','Cite as / arXiv-issued DOI via DataCite'],'supports':['Canonical title, author metadata/order, year, identifier, DOI, six-version history; no journal reference field is shown']},
 {'id':'arxiv_api','url':'https://export.arxiv.org/api/query?id_list=2507.06261','accessed_utc':access,'version':'v6','saved_file':'arxiv_api.xml','locations':['Atom entry/id','entry/title','entry/published','entry/updated','entry/author/name','absence of arxiv:journal_ref and arxiv:doi'],'supports':['Published 2025-07-07T17:36:04Z; updated 2025-12-19T14:25:46Z; 3435 parsed authors; no recorded journal reference']},
 {'id':'arxiv_fulltext','url':'https://arxiv.org/html/2507.06261v6','accessed_utc':access,'version':'v6','saved_file':'arxiv_v6.html','locations':['Title page: .ltx_authors','Abstract and Section 1','Section 3.1, Table 2 (#S3.T2)','Section 7, Contributors (#S7.p1.1.1.1)'],'supports':['Title-page collective byline Gemini Team, Google','Report includes Gemini 2.5 Pro; Table 2 maps it to gemini-2.5-pro','Full contributor list has 3424 named lines, including 11 parenthesized aliases']},
 {'id':'arxiv_pdf','url':'https://arxiv.org/pdf/2507.06261v6','accessed_utc':access,'version':'v6','saved_file':'arxiv_v6.pdf','locations':['PDF page 1, title/byline and left-margin version/date','PDF page 1, copyright line'],'supports':['Visually verified Gemini Team, Google byline, 2025 copyright and 19 Dec 2025 v6 timestamp'],'notes':'73 PDF pages; arXiv abstract Comments still says 72 pages. This is an upstream page-count discrepancy and irrelevant to cited metadata.'},
 {'id':'datacite','url':'https://api.datacite.org/dois/10.48550/arXiv.2507.06261','accessed_utc':access,'version':'attributes.version = 6','saved_file':'datacite.json','locations':['data.attributes.doi','publicationYear','titles[0].title','publisher','types.resourceTypeGeneral','types.bibtex','creators','relatedIdentifiers'],'supports':['DOI registered, arXiv publisher, 2025, Preprint, suggested BibTeX misc, version 6; 3435 creators; no related published-version identifier']},
 {'id':'google_pdf','url':'https://storage.googleapis.com/deepmind-media/gemini/gemini_v2_5_report.pdf','accessed_utc':access,'version':'unversioned official-hosted report, 73 pages observed','saved_file':None,'locations':['Page 1 title and byline (web text lines 0-4)'],'supports':['Independent official-hosted PDF also credits Gemini Team, Google'],'notes':'Opened full PDF text via web; web screenshot failed, so visual verification used downloaded arXiv v6 PDF instead. Unversioned Google PDF is not assumed byte-identical to v6.'},
 {'id':'google_model','url':'https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro','accessed_utc':access,'version':'Page last updated 2026-09-22 UTC; model latest update June 2025','saved_file':'google_model.html','locations':['Gemini 2.5 Pro heading','gemini-2.5-pro property table / Model code','Versions: Stable: gemini-2.5-pro','Latest update'],'supports':['Official API identity, exact stable model code, June 2025 release family'],'notes':'Current access policy is not evidence of experiment-time availability; it is not being cited as experimental performance evidence.'},
 {'id':'google_launch','url':'https://developers.googleblog.com/en/gemini-2-5-thinking-model-updates/','accessed_utc':access,'version':'17 June 2025 announcement','saved_file':'google_launch.html','locations':['Opening list','Continued growth of Gemini 2.5 Pro'],'supports':['General availability/stability; same model as 06-05 preview at launch; identifies gemini-2.5-pro model string']},
 {'id':'google_proprietary','url':'https://ai.google.dev/gemma/docs/core/model_card_4','accessed_utc':access,'version':'Last updated 2026-07-30 UTC','saved_file':'google_gemma_card.html','locations':['Ethics and Safety, first paragraph (web line 258)'],'supports':['Google explicitly refers to its proprietary Gemini models'],'notes':'Family-level corroboration for the proprietary label; not a Gemini 2.5-specific license text and not needed as a new main-text bibliography item.'}
]
for src in sources:
 f=src.get('saved_file')
 if f and (p/f).exists():src['sha256']=hashlib.sha256((p/f).read_bytes()).hexdigest()
evidence={
 'audit':'NEW Gemini 2.5 citation only; read-only to manuscript', 'accessed_utc':access,
 'manuscript':{'path':'paper/latex/acl_latex.tex','line':324,'citation_key':'comanici2025gemini25','claim':'proprietary Gemini 2.5 Pro among five evaluated LLM backbones'},
 'original_bib_entry':{'path':'paper/latex/custom.bib','start_line':459,'type':'article','author_count':3435,'saved_copy':'original_entry.bib'},
 'verdict':'Correct primary report and model identity; correct title/year/id/DOI; faithfully imported upstream author metadata is malformed relative to the report contributor list. Use actual collective byline Gemini Team.',
 'author_verification':comparison,
 'fulltext_contributor_count':3424,
 'all_metadata_vs_fulltext_differences':diffs,
 'substantive_split_name_count':11,
 'other_difference_count':8,
 'other_difference_interpretation':'Seven straight/curly apostrophe typography differences plus Marcáurelio versus Marc’aurelio. Tony Nguyễn also loses a diacritic within one of the eleven split-name cases.',
 'official_version_history':[{'v':1,'date':'2025-07-07T17:36:04Z'},{'v':2,'date':'2025-07-11T11:03:21Z'},{'v':3,'date':'2025-07-17T08:16:43Z'},{'v':4,'date':'2025-07-22T11:21:11Z'},{'v':5,'date':'2025-10-16T14:56:46Z'},{'v':6,'date':'2025-12-19T14:25:46Z'}],
 'formal_publication_status':{'verified':'Primary records identify an arXiv preprint; no journal/conference reference or related formal-publication DOI was found in arXiv/Atom/DataCite. Exact-title/Google primary-site searches did not find a publisher version.','limitation':'This is absence of recorded/discovered formal publication, not a proof no formal version exists anywhere.'},
 'claim_support':{'model_identity':'Direct: Abstract, Section 1, Section 3.1 Table 2; corroborated by official model card and release announcement.','proprietary':'Report describes AI Studio API evaluation, but does not explicitly call the model proprietary or state weights license. Official Google family-level wording corroborates proprietary.','actual_deployment':'A citation does not prove the experiment invoked the named model. Resolve experiment-specific endpoint/version, dates, provider, thinking/sampling from run records.','unrelated_performance':'Do not use Google benchmark tables as evidence for manuscript graph-retention/SA-MCGS comparisons.'},
 'style_test':{'engine':'/opt/homebrew/bin/tectonic, isolated directory','style':'exact unchanged copy of paper/latex/acl_natbib.bst','test_files':['audit_bibliography.tex','audit_bibliography.bib','audit_bibliography.bbl','audit_bibliography.pdf','audit_bibliography.log'],'original_render':'First 19 authors and 3416 others','short_author_plus_others_render':'Three explicit authors and 1 others','team_render':'Gemini Team. 2025.','warnings':[],'body_note':'The existing style already truncates displayed bibliography to 19 authors. The original does NOT literally print all 3435 names in the bibliography; its optional natbib author list and database remain huge.','existing_bbl_note':'paper/latex/acl_latex.bbl had no new Gemini entry when inspected; it was stale at audit time, so it cannot certify the current bibliography.'},
 'recommendation':{'author':'{{Gemini Team}}','keep_key':True,'minimal_type':'article','semantic_alternative':'misc','year':2025,'doi':'10.48550/arXiv.2507.06261','url':'https://arxiv.org/abs/2507.06261v6','note':'Version 6, 19 December 2025','reason':'Actual title-page group byline; avoids broken machine name parsing, wrong remaining-author count, huge metadata and the style-specific and-others bug. No .bst changes needed.','corporate_attribution_caveat':'Do not replace with Google DeepMind solely from a logo/publisher affiliation. Gemini Team is the actual byline.'},
 'sources':sources,
 'limitations':['arxiv.org/bibtex endpoint returned HTTP 406; used official HTML citation_author metadata, Atom API, DataCite, and fulltext cross-check instead.','doi.org web opener failed; DataCite API DOI lookup succeeded with HTTP 200.','No complete experiment provenance audit was performed by this Gemini-only subtask.']
}
(p/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
corrected='''@article{comanici2025gemini25,
    author  = {{Gemini Team}},
    title   = {{Gemini 2.5}: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities},
    journal = {arXiv preprint arXiv:2507.06261},
    year    = {2025},
    doi     = {10.48550/arXiv.2507.06261},
    url     = {https://arxiv.org/abs/2507.06261v6},
    note    = {Version 6, 19 December 2025},
}
'''
(p/'recommended_entry.bib').write_text(corrected)
rows='\n'.join('| '+str(x['metadata_positions'][0])+'–'+str(x['metadata_positions'][1])+' | '+' / '.join(x['metadata_names'])+' | '+x['fulltext_names'][0]+' |' for x in diffs if len(x['metadata_names'])==2)
report=f'''# Gemini 2.5 new-citation audit

Audit time: {access}. Scope: `comanici2025gemini25` and its model-identification use in §4.4, `paper/latex/acl_latex.tex:324`. This subtask made no manuscript or bibliography-style edits. The original bibliography entry is saved locally in `original_entry.bib`; raw primary-source snapshots and machine-readable evidence accompany this report.

## Decision

Keep this source. It is the correct primary technical report for Gemini 2.5 Pro. Its title, year, arXiv identifier, and DOI are correct. Replace the imported 3,435-name author field with the report’s actual group byline, `author = {{{{Gemini Team}}}}`, preserve the title and 2025, and pin the source to v6 with a visible version note. This is a bibliographic repair, not a change of model or a replacement with another paper.

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
| Actual report byline | not represented as such | arXiv HTML title page and visually inspected v6 PDF p. 1: “Gemini Team, Google”; official Google-hosted report has same byline | Use the collective author `{{Gemini Team}}`. Google identifies the organization; do not invent `Google DeepMind` as replacement author from the logo. |
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
{rows}

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
- `{{Gemini Team}}` prints **“Gemini Team. 2025.”**, compiles cleanly, and protects the collective name against personal-name parsing.
- The isolated test produced one PDF page, no BibTeX warnings, and no TeX warning/overfull/missing-character messages. It is a targeted bibliography test, not a full-paper layout certification.
- At the time inspected, `paper/latex/acl_latex.bbl` lacked this new entry entirely. The existing generated file was stale and could not be used to judge the revised bibliography; the parent task should rebuild the actual manuscript after applying corrections.

## Recommended concrete entry

This preserves the project’s existing arXiv-entry convention and changes only attribution and version specificity:

```bibtex
{corrected.rstrip()}
```

If the parent task standardizes preprints as `@misc`, use the same author/title/year/DOI/URL/note plus `eprint = {{2507.06261}}`, `archivePrefix = {{arXiv}}`, `primaryClass = {{cs.CL}}`, and a visible `howpublished = {{arXiv preprint arXiv:2507.06261}}`. Merely storing arXiv-specific fields does not guarantee that an older `.bst` renders them; inspect the result. Do not claim a journal, conference, volume, or pages not present in a primary record.

## Severity and limitations

**P2, repair before submission:** malformed upstream author metadata and inaccurate remaining-author count; the collective byline resolves these without modifying `acl_natbib.bst`. **No substantive citation mismatch:** this is the correct Gemini 2.5 Pro report. **Minor reproducibility improvement:** pin v6 in URL and note. **Evidence boundary:** the report supports model identity, while provider documentation supports routine proprietary classification; neither replaces actual execution provenance.

The arXiv BibTeX endpoint returned HTTP 406, and the web DOI opener failed. These did not prevent verification: the official HTML metadata, Atom API, full report, and DataCite registration were retrieved independently. The Google PDF screenshot endpoint failed; the downloaded arXiv v6 first page was rendered locally and visually inspected instead. Raw-source snapshots and SHA-256 hashes are listed in `evidence.json`.
'''
(p/'audit.md').write_text(report)
print('wrote',p/'audit.md',p/'evidence.json',p/'recommended_entry.bib')
