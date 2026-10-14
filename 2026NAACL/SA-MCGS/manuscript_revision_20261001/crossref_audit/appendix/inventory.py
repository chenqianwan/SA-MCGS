from pathlib import Path
import re,json
ROOT=Path('/Users/chenlong/WorkSpace/MCGS_Law')
OUT=ROOT/'tmp/crossref_audit_20261001/appendix'
files=['paper/latex/acl_latex.tex','paper/latex/revision_experiments.tex','paper/latex/revision_expert_appendix.tex','experiments/main_experiment/paper_assets/tables/five_model_appendix_breakdowns.tex']
def projection(s):
 mask=list(s)
 def blank(a,b):
  for k in range(a,b):
   if mask[k]!='\n':mask[k]=' '
 def group(pos):
  while pos<len(s) and s[pos].isspace():pos+=1
  assert s[pos]=='{',(pos,s[pos:pos+50])
  depth=1;i=pos+1
  while depth:
   if s[i]=='\\':i+=2;continue
   if s[i]=='{':depth+=1
   if s[i]=='}':depth-=1
   i+=1
  return pos,i
 for m in re.finditer(r'(?<!\\)%[^\n]*',s):blank(m.start(),m.end())
 for m in re.finditer(r'\\(revdel|revdeletedtable|revreplace|revnewreplace|revredreplace|revasset)\b',s):
  if mask[m.start()]==' ':continue
  a,b=group(m.end());blank(m.start(),b)
 return ''.join(mask)
refs=[];labels=[];hardcoded=[]
for name in files:
 s=(ROOT/name).read_text();p=projection(s);start=s.index('\\appendix') if name.endswith('acl_latex.tex') else 0
 for kind,arr,pat in [('reference',refs,r'\\(?:ref|eqref|pageref|autoref|cref|Cref)\{([^}]+)\}'),('label',labels,r'\\label\{([^}]+)\}'),('hardcoded',hardcoded,r'\b(?:Figure|Table|Algorithm|Appendix|Section|Panel)\s+[0-9A-Z][A-Za-z0-9.]*')]:
  for m in re.finditer(pat,p):
   if m.start()<start:continue
   ls=s.rfind('\n',0,m.start())+1;le=s.find('\n',m.end());le=len(s) if le==-1 else le
   arr.append({'file':name,'line':s.count('\n',0,m.start())+1,'key':m.group(1) if kind!='hardcoded' else m.group(0),'context':p[ls:le].strip()})
(OUT/'active_inventory.json').write_text(json.dumps({'references':refs,'labels':labels,'unlinked_panel_mentions':hardcoded},indent=2))
print('Active references',len(refs),'unique',len(set(x['key'] for x in refs)),'labels',len(labels),'panels',len(hardcoded))
for r in refs:print(f"{r['file']}:{r['line']} -> {r['key']}")
for r in hardcoded:print('UNLINKED',r['file'],r['line'],r['key'])
