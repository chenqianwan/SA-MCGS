"""Preserve previous black bibliography wording in the marked view only."""
from pathlib import Path
import re, json, importlib.util

ROOT=Path(__file__).resolve().parents[2]
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('crossrefs',ROOT/'tmp/crossref_audit_20261001/check_crossrefs.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

def entries(path):
    s=path.read_text();out={}
    matches=list(re.finditer(r'\\bibitem\[.*?\]\{([^}]+)\}',s,re.S))
    for n,m in enumerate(matches):
        end=matches[n+1].start() if n+1<len(matches) else s.index(r'\end{thebibliography}')
        out[m[1]]=s[m.end():end].strip()
    return out

def without_links(s):
    # Keep the actual visible title, omit only the obsolete hyperlink target.
    while m:=re.search(r'\\href\s*',s):
        a,b=helper.group(s,m.end());c,d=helper.group(s,b)
        s=s[:m.start()]+s[c+1:d-1]+s[d:]
    s=s.replace(r'\newblock',' ')
    return re.sub(r'\s+',' ',s).strip()

def old_plain(s):
    s=without_links(s)
    while m:=re.search(r'\\emph\s*',s):
        a,b=helper.group(s,m.end())
        s=s[:m.start()]+s[a+1:b-1]+s[b:]
    return s

old=entries(P/'before/acl_latex_clean.bbl')
new=entries(P/'clean_build/acl_latex_clean.bbl')
changed=json.loads((P/'changed_keys.json').read_text())
lines=['% October 1 full bibliography audit. Only the marked PDF shows old text.',
       '% Generated from the pre-audit compiled bibliography; old links are omitted.']
visible_changes=[]
for k in changed:
    if k not in new:continue
    lines += [r'\csdef{fullbibaudit@'+k+'}{1}']
    if without_links(old[k])!=without_links(new[k]):
        visible_changes.append(k)
        lines += [r'\csdef{fullbibprevious@'+k+r'}{\revdel{'+old_plain(old[k])+'}}']
(ROOT/'paper/latex/revision_bibliography_audit.tex').write_text('\n'.join(lines)+'\n')
(P/'visible_bib_changes.json').write_text(json.dumps(visible_changes,indent=2)+'\n')
print('Marked entries',sum(k in new for k in changed),'old visible entries retained',len(visible_changes))
