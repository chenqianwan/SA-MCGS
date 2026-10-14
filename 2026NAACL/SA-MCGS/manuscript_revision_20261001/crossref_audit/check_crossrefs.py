"""Audit this manuscript's clean references against fresh TeX/PDF destinations.

The projection only implements revision macros used in this repository. It is
not a general TeX interpreter. Fresh aux files and independent content review
remain the authority for numbers, locations, and semantic correspondence.
"""
from pathlib import Path
from collections import Counter
import argparse, json, re
from pypdf import PdfReader

ROOT = Path('/Users/chenlong/WorkSpace/MCGS_Law')
LATEX = ROOT / 'paper/latex'
AUDIT = ROOT / 'tmp/crossref_audit_20261001'

def group(s, start):
    while s[start].isspace(): start += 1
    assert s[start] == '{', (start, s[start:start+80])
    level, i = 1, start+1
    while level:
        if s[i] == '\\': i += 2; continue
        if s[i] == '{': level += 1
        if s[i] == '}': level -= 1
        i += 1
    return start, i

def project(s):
    chars = list(s)
    def hide(a,b):
        for i in range(a,b):
            if chars[i] != '\n': chars[i] = ' '
    for m in re.finditer(r'(?<!\\)%[^\n]*',s): hide(*m.span())
    s = ''.join(chars)
    for m in re.finditer(r'\\ifrevisionmarks\b.*?\\fi\b',s,re.S): hide(*m.span())
    for m in re.finditer(r'\\(revdel|revdeletedtable|revreplace|revnewreplace|revredreplace|revasset)\b',s):
        a,b = group(s,m.end())
        hide(m.start(),b)
    return ''.join(chars)

def read_sources(path, seen):
    if path in seen: return
    seen.add(path)
    raw=path.read_text(); visible=project(raw)
    yield path, raw, visible
    for m in re.finditer(r'\\input\{([^}]+)\}',visible):
        if m[1]=='revision_markup': continue
        child=(LATEX/m[1]).with_suffix('.tex').resolve()
        yield from read_sources(child,seen)

def read_aux(path):
    s=path.read_text(); entries=[]
    for m in re.finditer(r'\\newlabel\{([^}]+)\}',s):
        a,b=group(s,m.end()); inside=s[a+1:b-1]; vals=[]; i=0
        while i<len(inside):
            a2,b2=group(inside,i);vals.append(inside[a2+1:b2-1]);i=b2
        entries.append({'key':m[1],'number':vals[0],'page':int(vals[1]),'caption_or_section':vals[2],'anchor':vals[3]})
    return entries

def run(stage):
    results={}
    entries_by_view={}
    for view,stem in [('clean','acl_latex_clean'),('marked','acl_latex')]:
        folder=AUDIT/(view+'_build')
        entries=read_aux(folder/(stem+'.aux'));entries_by_view[view]=entries
        reader=PdfReader(folder/(stem+'.pdf'))
        destinations=reader.named_destinations
        destpages={k:reader.get_destination_page_number(v)+1 for k,v in destinations.items()}
        broken=[];internals=0
        for page_no,page in enumerate(reader.pages,1):
            for ann in page.get('/Annots',[]):
                ann=ann.get_object(); dest=ann.get('/Dest')
                action=ann.get('/A')
                if action and action.get('/S')=='/GoTo':dest=action.get('/D')
                if dest is not None and isinstance(dest,str):
                    internals+=1
                    if dest not in destinations:broken.append({'page':page_no,'target':dest})
        mismatches=[e for e in entries if e['anchor'] and destpages.get(e['anchor']) != e['page']]
        log=(folder/(stem+'.log')).read_text(errors='replace')
        warnings=[l for l in log.splitlines() if any(w in l.lower() for w in ['undefined','multiply defined'])]
        results[view]={'pages':len(reader.pages),'labels':entries,'duplicate_label_keys':[k for k,v in Counter(e['key'] for e in entries).items() if v>1],
            'named_destinations':len(destinations),'internal_named_links':internals,'broken_internal_links':broken,'label_anchor_page_mismatches':mismatches,'undefined_or_duplicate_warnings':warnings}
    labels={e['key']:e for e in entries_by_view['clean']}
    refs=[]
    for path,raw,s in read_sources(LATEX/'acl_latex.tex',set()):
        for m in re.finditer(r'\\(?:ref|pageref|eqref|autoref|[cC]ref)\{([^}]+)\}',s):
            ctx=re.sub(r'\s+',' ',s[max(0,m.start()-90):m.end()+100]).strip()
            refs.append({'file':str(path.relative_to(ROOT)),'line':raw[:m.start()].count('\n')+1,'key':m[1],'context':ctx,'destination':labels.get(m[1])})
    used=Counter(r['key'] for r in refs)
    floats=[e for e in entries_by_view['clean'] if e['key'].startswith(('fig:','tab:','alg:'))]
    for e in floats:e['explicit_reference_count']=used[e['key']]
    results['active_clean_refs']=refs
    results['summary']={'reference_instances':len(refs),'distinct_targets':len(used),'missing_targets':[r for r in refs if r['destination'] is None],
        'figure_count':len({e['anchor'] for e in floats if e['key'].startswith('fig:')}),'table_count':len({e['anchor'] for e in floats if e['key'].startswith('tab:')}),'algorithm_count':len({e['anchor'] for e in floats if e['key'].startswith('alg:')})}
    (AUDIT/(stage+'_crossref_checks.json')).write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(results['summary'],ensure_ascii=False))
    print(json.dumps({v:{k:x for k,x in results[v].items() if k not in ['labels']} for v in ['clean','marked']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage');run(p.parse_args().stage)
