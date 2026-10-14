from pathlib import Path
import importlib.util,re,json,hashlib
from collections import Counter
import fitz
from pypdf import PdfReader

P=Path(__file__).resolve().parent;ROOT=P.parents[1]
spec=importlib.util.spec_from_file_location('refs',ROOT/'tmp/crossref_audit_20261001/check_crossrefs.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
data=json.loads((P/'full_audit.json').read_text())
out={}
for view,stem in [('clean','acl_latex_clean'),('marked','acl_latex')]:
    folder=P/(view+'_build');bbl=(folder/(stem+'.bbl')).read_text();log=(folder/(stem+'.log')).read_text()
    keys=re.findall(r'\\bibitem\[.*?\]\{([^}]+)\}',bbl,re.S)
    reader=PdfReader(folder/(stem+'.pdf'));dests=reader.named_destinations
    labels=h.read_aux(folder/(stem+'.aux'));badlinks=[]
    for n,p in enumerate(reader.pages,1):
        for ref in p.get('/Annots',[]):
            a=ref.get_object();dst=a.get('/Dest');action=a.get('/A')
            if action and action.get('/S')=='/GoTo':dst=action.get('/D')
            if isinstance(dst,str) and dst not in dests:badlinks.append({'page':n,'dest':dst})
    doc=fitz.open(folder/(stem+'.pdf'));location={}
    for n,p in enumerate(doc,1):
        t=p.get_text()
        if '8\nConclusion' in t:location['conclusion_page']=n
        if re.search(r'\bLimitations\b',t):location.setdefault('limitations_start',n)
        if re.search(r'\bReferences\b',t):location.setdefault('references_start',n)
    out[view]={
        'pages':len(reader.pages),'bibliography_entries':len(keys),'unique_bibliography_entries':len(set(keys)),
        'missing_bib_keys':sorted(k for k,x in data.items() if x['cited_in_pdf'] and k not in keys),
        'extra_bib_keys':sorted(k for k in keys if k not in data or not data[k]['cited_in_pdf']),
        'broken_internal_links':badlinks,
        'label_page_mismatches':[e['key'] for e in labels if e['anchor'] and reader.get_destination_page_number(dests[e['anchor']])+1!=e['page']],
        'duplicate_label_keys':[k for k,n in Counter(e['key'] for e in labels).items() if n>1],
        'unresolved_reference_warnings':[l for l in log.splitlines() if 'undefined' in l.lower() or 'multiply defined' in l.lower()],
        'bibtex_warnings':[l for l in (folder/(stem+'.blg')).read_text().splitlines() if 'Warning' in l],
        'overfull_warnings':[l for l in log.splitlines() if 'Overfull' in l],
        'sha256':hashlib.sha256((folder/(stem+'.pdf')).read_bytes()).hexdigest(),**location}
    out[view]['float_numbers']={e['key']:e['number'] for e in labels if e['key'].startswith(('fig:','tab:','alg:'))}
cleanlabels={e['key'] for e in h.read_aux(P/'clean_build/acl_latex_clean.aux')}
refs=[];cites=[]
for path,raw,s in h.read_sources(ROOT/'paper/latex/acl_latex.tex',set()):
    refs += re.findall(r'\\(?:ref|eqref|pageref)\{([^}]+)\}',s)
    for group in re.findall(r'\\cite\w*\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}',s):cites += group.split(',')
out['active_reference_instances']=len(refs);out['missing_crossref_labels']=sorted(set(refs)-cleanlabels)
out['active_citation_occurrences']=len(cites);out['active_citation_keys']=len(set(cites))
out['audited_entries']=len(data);out['unused_entries']=sum(not x['cited_in_pdf'] for x in data.values())
out['printed_entries_with_errors']=sum(bool(x.get('errors')) and x['cited_in_pdf'] for x in data.values())
out['printed_entries_with_field_changes']=sum(bool(x['field_changes'] or x['type_change']) and x['cited_in_pdf'] for x in data.values())
out['printed_originals_unchanged']=sum(not(x['field_changes'] or x['type_change']) and x['cited_in_pdf'] for x in data.values())
out['all_stored_manual_others_removed']=' and others' not in (ROOT/'paper/latex/custom.bib').read_text()
out['official_style_unchanged']=hashlib.sha256((ROOT/'paper/latex/acl_natbib.bst').read_bytes()).digest()==hashlib.sha256((P/'before/acl_natbib.bst').read_bytes()).digest()
(P/'final_verification.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
