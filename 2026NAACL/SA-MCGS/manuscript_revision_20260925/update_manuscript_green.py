"""Apply this round to the main TeX, preserving original black text as deletions."""
from pathlib import Path
import json
import re

REV = Path(__file__).resolve().parent
ROOT = REV.parents[2]
TEX = ROOT / 'paper/latex'
source = (REV/'latex_before_green/acl_latex.tex').read_text()
s = source
changes = []

def arg(text, pos):
    while text[pos].isspace(): pos += 1
    assert text[pos] == '{', text[pos:pos+50]
    start = pos + 1
    depth = 1; pos += 1
    while depth:
        if text[pos] == '\\': pos += 2; continue
        if text[pos] == '{': depth += 1
        elif text[pos] == '}': depth -= 1
        pos += 1
    return text[start:pos-1], pos

def original(text):
    """Recover black text from the previous blue revision, without expanding inputs."""
    out=[];pos=0
    pattern=re.compile(r'\\(revadd|revdel|revreplace)\b|\\begin\{revadded\}')
    while m:=pattern.search(text,pos):
        out.append(text[pos:m.start()])
        if m.group(0)==r'\begin{revadded}':
            end=text.index(r'\end{revadded}',m.end());pos=end+len(r'\end{revadded}');continue
        a,pos=arg(text,m.end());kind=m[1]
        if kind=='revreplace':
            _,pos=arg(text,pos);out.append(original(a))
        elif kind=='revdel':out.append(original(a))
    out.append(text[pos:]);return ''.join(out)

def substitute(old,new,reason):
    global s
    assert s.count(old)==1,(reason,s.count(old),old[:100])
    s=s.replace(old,new,1);changes.append({'reason':reason,'before':old,'after':new})

def prose(old,new,reason):
    black=original(old)
    if black.strip():
        out=(r'\revnewreplace{' + black + '}{' + new + '}') if new else (r'\revdel{' + black + '}')
    else:out=r'\revnew{' + new + '}' if new else ''
    substitute(old,out,reason)

def paragraph_after(marker,new,reason):
    start=s.index(marker)+len(marker)
    while s[start]=='\n':start+=1
    end=s.index('\n\n',start)
    prose(s[start:end],new,reason)

def replace_revreplace_containing(needle,new,reason):
    for m in re.finditer(r'\\revreplace\{',s):
        a,end=arg(s,m.end()-1);b,end=arg(s,end)
        if needle in a or needle in b:
            prose(s[m.start():end],new,reason);return
    raise AssertionError(needle)

substitute('% Author revision view: blue additions and struck-through replaced/deleted text.',
           '% Revision view: earlier additions blue, September 25 additions green; original deletions struck.',
           'Revision color legend')
replace_revreplace_containing('Across 320 model-case pairs and four LLMs',
    r'Across five LLMs and 400 model-cases, \samcgs{} improves root localization and complete risk-evidence extraction over One-shot prompting and local evidence aggregation (LEA). For GPT-4o and Qwen2.5-72B, it raises \riskall{} from 43.75\% with LEA to 75.00\%.',
    'Abstract five-model evidence')
replace_revreplace_containing('The gains are larger under long-context pressure',
    r'Component ablations, measured inference costs, and a blinded expert audit further support its use for extracting compact, inspectable evidence from cyclic document graphs.',
    'Abstract concluding evidence')
prose('The benchmark contains 320 model-case pairs evaluated with GPT-4o, DeepSeek-V3, Qwen2.5-72B, and Gemini 2.5 Pro.',
    'The benchmark contains 80 injected variants evaluated with five LLMs, yielding 400 model-cases.',
    'Contribution sample/model scope')
replace_revreplace_containing('Across these settings,',
    r'Comparisons with One-shot prompting and LEA show gains in root localization, complete endpoint retention, and compact evidence extraction. Component ablations, inference costs, and expert auditing connect these gains to the search design and the evidence returned.',
    'Contribution current evidence')

prose('over the same \\scc{} blocks and models for both methods.',
    r'over the same \scc{} blocks and models for all three methods.', 'Three-method shared inputs')
prose('Both methods receive the same generic risk semantics and the same visible graph;',
    'All three methods receive the same generic risk semantics and the same visible graph;', 'Three-method shared rubric')
old_blue=r'\revadd{We evaluate 80 injected variants across four domains using four LLMs, yielding 320 model-case evaluations. The matched comparison with LEA uses a subset balanced across the three legal domains and four injection templates.}'
prose(old_blue,
    r'The 20 source \scc{}s each contribute four injected variants, giving the same 80 cases per model. Five models and three methods yield 400 model-cases and 1,200 method outputs.',
    'Setup current sample scale')
prose('We evaluate GPT-4o, DeepSeek-V3, Qwen2.5-72B-Instruct, and Gemini 2.5 Pro.',
    'We evaluate GPT-4o, Gemini 2.5 Pro, Qwen2.5-72B, Llama 3.1-8B-Instruct, and Qwen3.5-9B.',
    'Model list')
replace_revreplace_containing('The main comparison contains 320 model-case pairs per method;',
    r'One-shot, LEA, and \samcgs{} are compared on all 80 cases for each model. The separate cost comparison uses 12 source \scc{}s and two models.',
    'Main and specialist experiment scope')

# Existing figures keep labels and original captions as struck-through text.
def figure_update(old_asset,new_asset,new_caption,reason):
    pos=s.index('{'+old_asset+'}')
    cap=s.index(r'\caption{',pos);oldcap,end=arg(s,cap+len(r'\caption'))
    substitute(s[cap:end],r'\caption{\revnewreplace{'+original(oldcap)+'}{'+new_caption+'}}',reason+' caption')
    substitute('{'+old_asset+'}',r'{\revasset{'+old_asset+'}{'+new_asset+'}}',reason+' asset')

figure_update('fig02_main_results_composite.pdf','fig02_main_results_five_models.pdf',
    r'Three-method comparison by \scc{} size. Columns show the five models; rows show \rootthree{} and \riskall{}. All methods use the same small ($\leq12$ nodes), medium (14--20), and large ($\geq24$) case groups. Gray circles denote One-shot, orange squares LEA, and blue triangles \samcgs{}.',
    'Five-model size figure')
replace_revreplace_containing('Figure~\\ref{fig:main_metrics} shows the core result.', '',
    'Retire superseded pooled oracle result')
prose('The compression axis should be read as a trade-off, not a loss.  Oracle-risk \\naive{} is slightly more compressed on average, but still retains all critical endpoints less often.  \\samcgs{} deliberately keeps a larger dynamic core when evidence persists across rollouts.',
    r'Figure~\ref{fig:coverage_compression} connects complete evidence retention with output size. For Qwen3.5-9B, \samcgs{} improves \rootthree{} over LEA from 56.25\% to 62.50\% and compression from 51.26\% to 67.25\%, while maintaining \riskall{} at 63.75\%. For GPT-4o, the higher \riskall{} is obtained at the same 51.26\% mean compression as LEA. These comparisons show how search improves evidence selection within compact outputs.',
    'Coverage-compression interpretation')
prose(r'\revreplace{Appendix}{Table}~\ref{tab:reliability} separates one-shot output availability from boosted raw-attempt and model-case reliability.', '',
    'Retire old reliability digression from main results')
scatter=r'''
\begin{revnewblock}
\begin{figure*}[t]
    \centering
    \includegraphics[width=\textwidth]{fig03_coverage_compression_five_models.pdf}
    \caption{Complete evidence retention and compression. Each panel shows one model with three method-level points from Table~\ref{tab:matched_main}; all panels share percentage axes. Higher positions retain all target endpoints more often, and rightward positions use smaller subgraphs.}
    \label{fig:coverage_compression}
\end{figure*}
\end{revnewblock}

'''
substitute(r'\subsection{Breakdown by model and domain}',scatter+r'\subsection{Breakdown by model and domain}',
    'Add coverage-compression figure')
paragraph_after(r'\subsection{Breakdown by model and domain}',
    r'The model-level gains also appear in the domain breakdowns in Table~\ref{tab:appendix_breakdowns}. Pooling the five models, \samcgs{} raises \riskall{} over LEA from 26.67\% to 51.67\% on BGB and from 53.00\% to 69.00\% on CUAD. These comparisons extend the completeness gains to statutory cross-references and longer contract-clause graphs.',
    'Model/domain synthesis')

# Numerical size and budget interpretations are finalized after asset validation.
paragraph_after(r'\subsection{Effect of SCC size}',
    r'Figure~\ref{fig:main_metrics} shows that \samcgs{} improves \riskall{} over LEA in all three size groups for GPT-4o and Qwen2.5-72B. The largest gains for these models occur in medium components, at 37.50 and 62.50 percentage points, respectively. Llama 3.1-8B-Instruct also improves \rootthree{} in every size group. Table~\ref{tab:appendix_breakdowns} gives the full size breakdown.',
    'Size analysis linked to current groups')
figure_update('fig04_budget_prefix_convergence.pdf','fig04_budget_prefix_three_methods.pdf',
    r'GPT-4o evidence retention and compression over 60 rollout prefixes on the same 80 cases. The solid curve shows \samcgs{}; horizontal reference lines show the final One-shot and LEA scores. Each prefix uses the saved search evidence and the final-core selection rule, with budget 60 aligned to the final outputs.',
    'Budget figure')
start=s.index('Figure~\\ref{fig:convergence} shows that additional rollouts')
end=s.index('\n\n',start)
prose(s[start:end],
    r'Figure~\ref{fig:convergence} shows that most completeness gains emerge within the first 20 rollouts: \riskall{} rises from 25.00\% at budget 5 to 76.25\% at budget 20. Subsequent rollouts update the retained core, ending at 75.00\% \riskall{} and 51.26\% compression at budget 60. The final points match the GPT-4o results in Table~\ref{tab:matched_main}.',
    'Budget interpretation uses aligned output metrics')
paragraph_after(r'\subsection{Robustness checks}',
    r'We examine the search components and final-core policy below, and report the prior-sensitivity results alongside measured inference costs. Appendix~\ref{sec:appendix_case} compares the three methods on the same long-\scc{} case.',
    'Robustness links current support instead of retired pooled controls')

replace_revreplace_containing('Across four domains and four LLMs, this yields',
    r'Across four domains and five LLMs, the comparisons with One-shot prompting and LEA show improvements in root localization, complete risk-evidence extraction, and subgraph compactness. Core-policy replay and expert auditing connect these gains to the evidence selected and retained. Together, the results support \samcgs{} as a way to turn cyclic dependencies into focused evidence for human inspection.',
    'Unified five-model conclusion')
oldlim=r'\revreplace{Naturally occurring risks may be less controlled and require human audit.}'
start=s.index(oldlim);a,end=arg(s,start+len(r'\revreplace'));b,end=arg(s,end)
newb=b.replace(' LEA comparisons cover two models rather than the full four-model collection.','')
substitute(s[start:end],r'\revdel{'+a+r'}\revnew{'+newb+'}', 'Remove obsolete LEA coverage limitation')

figure_update('fig06_representative_scc_collapse.pdf','fig06_representative_scc_three_methods.pdf',
    r'Three methods on the same 25-record BGB case with Gemini 2.5 Pro. Node positions and evidence roles are shared across panels; colored nodes are retained and gray nodes are omitted. The injected root is \S505 and the witness is \S491. Each panel reports the retained node count and the four evaluation metrics.',
    'Same-case three-method figure')
start=s.index('Figure~\\ref{fig:case} illustrates the intended use');end=s.index('\n\n',start)
prose(s[start:end],
    r'Figure~\ref{fig:case} compares three ways to organize evidence from the same cyclic region. One-shot retains three records but omits the root. LEA and \samcgs{} both retain all risk endpoints; \samcgs{} uses nine records rather than LEA\textquotesingle s twelve, increasing compression from 52\% to 64\%. The shared layout makes the retained constraint and its distant witness directly comparable.',
    'Case interpretation grounded in shared layout')

prose(r'both full-\scc{} \naive{} attempts and the \samcgs{} local-window evaluator',
    r'One-shot prompting and the local-window evaluators used by LEA and \samcgs{}',
    'Shared rubric includes LEA')
prose(r'for \naive{} and \samcgs{} under the same model and profile.',
    r'for One-shot, LEA, and \samcgs{} under the same model and profile.',
    'Dataset construction shared by three methods')
substitute(' The ten-attempt oracle-risk selector is reported separately as a ground-truth-assisted reference.',
    '', 'Remove obsolete blue selector-results pointer')

# Retired black tables remain visible and struck in the marked version only.
def strike_table(text):
    text=original(text)
    lines=[]
    for line in text.splitlines():
        if '&' in line and re.search(r'\\\\\s*$',line):
            content=line[:line.rfind(r'\\')]
            parts=content.split('&')
            line=' & '.join(r'\revdel{'+v.strip()+'}' if v.strip() else '' for v in parts)+r' \\'
        elif line.startswith(r'\textbf{'):
            content,end=arg(line,len(r'\textbf'))
            line=r'\revdel{\textbf{'+content+'}}'+line[end:]
        lines.append(line)
    text='\n'.join(lines)
    # Original captions are textual deletions; keep old labels separate from replacements.
    output=[];pos=0
    for m in re.finditer(r'\\caption\{',text):
        a,end=arg(text,m.end()-1)
        output.append(text[pos:m.start()]+r'\caption{\revdel{'+a+'}}');pos=end
    output.append(text[pos:]);text=''.join(output)
    text=re.sub(r'\\label\{([^{}]+)\}',r'\\revoldlabel{\1}',text)
    return r'\revdeletedtable{'+'\n'+text+'\n}\n'

start=s.index(r'\paragraph{Locked run configuration.}')
end=s.index(r'\input{revision_experiments}',start)
old_appendix=s[start:end]
first_table=old_appendix.index(r'\begin{table*}')
old_config=original(old_appendix[:first_table]).strip()
heading=r'\paragraph{Locked run configuration.}'
configbody=old_config[len(heading):].strip()
config_marked=r'\revdel{'+configbody+'}'
# Let the monospace profile break at its spaces inside the deletion.
for cm in list(re.finditer(r'\\texttt\{',configbody)):
    value,end=arg(configbody,cm.end()-1)
    original_code=configbody[cm.start():end]
    config_marked=config_marked.replace(original_code,r'}\texttt{\revdel{'+value+r'}}\revdel{')
retired=r'\revdeletedtable{\paragraph{\revdel{Locked run configuration.}}'+config_marked+'}\n\n'
rest=old_appendix[first_table:]
# Process each float while retaining the original order and inter-float whitespace.
parts=[];pos=0
for m in re.finditer(r'\\begin\{(table\*|figure\*)\}',rest):
    if m.start()<pos:continue
    endmarker=r'\end{'+m[1]+'}'
    stop=rest.index(endmarker,m.end())+len(endmarker)
    parts.append(rest[pos:m.start()]);parts.append(strike_table(rest[m.start():stop]));pos=stop
parts.append(rest[pos:]);retired+=''.join(parts)
(TEX/'revision_retired_controls.tex').write_text(retired)
new_appendix=r'''\begin{revnewblock}
\paragraph{Locked run configuration.}
All five models use the same 80 injected variants from 20 source \scc{}s. One-shot, LEA, and \samcgs{} follow the shared risk rubric and fixed method configurations described in Appendix~\ref{app:revision_experiments}. Table~\ref{tab:appendix_breakdowns} reports their model-, domain-, and size-level results.
\end{revnewblock}

\input{revision_retired_controls}

\begin{revnewblock}
\input{../../experiments/main_experiment/paper_assets/tables/five_model_appendix_breakdowns}
\end{revnewblock}

'''
substitute(old_appendix,new_appendix,'Replace obsolete appendix comparison; retain struck black tables')
(TEX/'acl_latex.tex').write_text(s)
(REV/'main_tex_green_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print('Applied',len(changes),'main-text edits; black originals retained.')
