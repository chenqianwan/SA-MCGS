"""Verify original black wording survives and current prose has consistent scope."""
from pathlib import Path
import difflib
import json
import re

REV=Path(__file__).resolve().parent
ROOT=REV.parents[2]
TEX=ROOT/'paper/latex'

def uncomment(s):return re.sub(r'(?<!\\)%[^\n]*','',s)
def arg(s,p):
    while s[p].isspace():p+=1
    assert s[p]=='{',(p,s[p:p+60])
    start=p+1;depth=1;p+=1
    while depth:
        if s[p]=='\\':p+=2;continue
        if s[p]=='{':depth+=1
        elif s[p]=='}':depth-=1
        p+=1
    return s[start:p-1],p

def view(s,mode,directory):
    s=uncomment(s);out=[];p=0
    pat=re.compile(r'\\(revnewreplace|revreplace|revnew|revadd|revdel|revdeletedtable|revasset|revoldlabel|input)\b|\\begin\{(revadded|revnewblock)\}')
    while m:=pat.search(s,p):
        out.append(s[p:m.start()])
        if m[2]:
            endtag=r'\end{'+m[2]+'}'
            end=s.index(endtag,m.end())
            if mode=='clean':out.append(view(s[m.end():end],mode,directory))
            p=end+len(endtag);continue
        kind=m[1];a,p=arg(s,m.end())
        if kind in ('revreplace','revnewreplace','revasset'):
            b,p=arg(s,p);out.append(view(a if mode=='old' else b,mode,directory))
        elif kind in ('revadd','revnew'):
            if mode=='clean':out.append(view(a,mode,directory))
        elif kind in ('revdel','revdeletedtable'):
            if mode=='old':out.append(view(a,mode,directory))
        elif kind=='revoldlabel':out.append(r'\label{'+a+('' if mode=='old' else ':previous')+'}')
        else:
            if a=='revision_markup':continue
            path=directory/(a if a.endswith('.tex') else a+'.tex')
            out.append(view(path.read_text(),mode,path.parent))
    out.append(s[p:]);return ''.join(out)

def body(s):return s.split(r'\begin{document}',1)[1].split(r'\end{document}',1)[0]
def normalize(s):
    s=re.sub(r'\\(?:sub)*section\*?\{\s*\}','',s)
    return re.findall(r'\\[A-Za-z]+|\\.|[^\s]',s)

baseline_dir=REV/'latex_before_green'
baseline=view(body((baseline_dir/'acl_latex.tex').read_text()),'old',baseline_dir)
current=body((TEX/'acl_latex.tex').read_text())
restored=view(current,'old',TEX)
clean=view(current,'clean',TEX)
a,b=normalize(baseline),normalize(restored)
diff=[]
if a!=b:
    for tag,aa,bb,cc,dd in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if tag!='equal':diff.append({'op':tag,'before':''.join(a[aa:bb]),'after':''.join(b[cc:dd])})
(REV/'current_clean_body.tex').write_text(clean)
(REV/'restored_original_black.tex').write_text(restored)
report={
    'original_black_normalized_exact_match':a==b,
    'black_differences':diff,
    'excluded_models_in_clean':re.findall(r'DeepSeek|Kimi',clean),
    'obsolete_current_scope_in_clean':re.findall(r'320|3,200|four-model|four LLMs|LEA comparisons cover two',clean),
    'unresolved_revision_commands_in_clean':re.findall(r'\\(?:revnew|revadd|revreplace|revdeletedtable|revoldlabel|input)\b',clean),
    'empty_headings_in_clean':re.findall(r'\\(?:sub)*section\*?\{\s*\}',clean),
}
(REV/'green_revision_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
