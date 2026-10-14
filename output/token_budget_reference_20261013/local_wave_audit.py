#!/usr/bin/env python3
"""Read-only audit of the three local-model cohorts used by paper Fig.3/Table15.

Only the JSON adjacent to this script is written. Remote code reads frozen
final.json and (optionally) per-arm ledgers; it never imports experiment runners.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

ROOT = Path('/Users/chenlong/WorkSpace/MCGS_Law')
EXP = ROOT / '2026NAACL/SA-MCGS/experiments'
WAVES = ['equal_budget_all80_20261009', 'equal_budget_all80_wave2_20261010', 'equal_budget_all80_wave3_20261010']
OUT = Path(__file__).with_suffix('.json')

REMOTE = r'''
from pathlib import Path
import json,hashlib
root=Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law')
waves=['equal_budget_all80_20261009','equal_budget_all80_wave2_20261010','equal_budget_all80_wave3_20261010']
out={'remote_root':str(root),'waves':[],'rows':[]}
for wi,name in enumerate(waves,1):
 p=root/name
 ref=p/'historical_sa_reference.json'
 out['waves'].append({'wave':wi,'directory':name,'reference_sha256':hashlib.sha256(ref.read_bytes()).hexdigest()})
 for f in sorted((p/'results').glob('*/*/*/final.json')):
  raw=f.read_bytes();d=json.loads(raw)
  row={k:d.get(k) for k in ['model_key','method','case_uid','case_id','main_case_order','domain','source_n','token_budget','historical_sa_source_sha256','completion_status','usage','metrics','error_type']}
  row.update(wave=wi,source_path=str(f),source_sha256=hashlib.sha256(raw).hexdigest(),selection=d.get('inference',{}).get('selection',{}))
  out['rows'].append(row)
print(json.dumps(out,separators=(',',':')))
'''

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def remote_read(code):
    for attempt in range(3):
        p = subprocess.run(['ssh','-o','ConnectTimeout=20','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=2','Group3_slogin','python3','-'],input=code,text=True,capture_output=True)
        if p.returncode == 0:
            return json.loads(p.stdout)
        if attempt == 2 or ('UNKNOWN port 65535' not in p.stderr and 'Connection closed' not in p.stderr):
            raise RuntimeError(p.stderr)
        time.sleep(2)

def brief(r):
    return {k:r[k] for k in ['wave','case_uid','main_case_order','token_budget','actual_tokens','actual_to_reference_ratio','completion_status'] if k in r}

def summarize(rows, reference_total):
    keys = set().union(*(r['usage'].keys() for r in rows))
    usage = {k:sum(r['usage'].get(k,0) for r in rows) for k in sorted(keys)
             if all(isinstance(r['usage'].get(k,0),(int,float)) for r in rows)}
    lo=min(rows,key=lambda r:r['actual_to_reference_ratio'])
    hi=max(rows,key=lambda r:r['actual_to_reference_ratio'])
    return {'rows':len(rows),'states':dict(Counter(r['completion_status'] for r in rows)),
            'usage':usage,'reference_tokens':reference_total,
            'actual_to_reference_ratio':usage['total_tokens']/reference_total,
            'actual_minus_reference_tokens':usage['total_tokens']-reference_total,
            'over_cap_cases':sum(r['actual_tokens']>r['token_budget'] for r in rows),
            'cap_mismatch_cases':sum(not r['cap_matches_reference'] for r in rows),
            'min_case_utilization':brief(lo),'max_case_utilization':brief(hi),
            'max_absolute_unused_tokens':brief(max(rows,key=lambda r:r['token_budget']-r['actual_tokens'])),
            'case_utilization_mean':statistics.mean(r['actual_to_reference_ratio'] for r in rows),
            'case_utilization_median':statistics.median(r['actual_to_reference_ratio'] for r in rows),
            'selector_statuses':dict(Counter(r['selection'].get('status','not_returned') for r in rows)),
            'judge_tokens_known_from_selection':sum(r['selection'].get('judge_tokens',0) for r in rows)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reuse',action='store_true',help='Reuse already captured remote final records')
    args=parser.parse_args()
    old=json.loads(OUT.read_text()) if args.reuse else None
    remote=old['remote'] if old else remote_read(REMOTE)
    refpath=EXP/WAVES[0]/'historical_sa_reference.json'
    refraw=json.loads(refpath.read_text())
    refs={(r['model_key'],r['case_uid']):r for r in refraw['rows']}
    assert len(refs)==240
    assert all(w['reference_sha256']==sha(refpath) for w in remote['waves'])
    for r in remote['rows']:
        ref=refs[(r['model_key'],r['case_uid'])]
        r['reference_tokens']=ref['usage']['total_tokens']
        r['cap_matches_reference']=r['token_budget']==r['reference_tokens']
        r['source_reference_hash_matches']=r['historical_sa_source_sha256']==ref['source_sha256']
        r['actual_tokens']=r['usage']['total_tokens']
        r['actual_to_reference_ratio']=r['actual_tokens']/r['reference_tokens']
        assert r['usage']['prompt_tokens']+r['usage']['completion_tokens']==r['actual_tokens']
        assert r['source_reference_hash_matches']
    assert len(remote['rows'])==len({(r['wave'],r['model_key'],r['case_uid'],r['method']) for r in remote['rows']})==1440
    hist=[]
    for model in ['llama','kimi','qwen35']:
        rr=[r for r in refs.values() if r['model_key']==model]
        rawrows=[]
        for r in rr:
            p=Path(r['source_file']);raw=p.read_bytes();d=json.loads(raw)
            assert hashlib.sha256(raw).hexdigest()==r['source_sha256']
            assert all(d['llm_usage_summary'][k]==r['usage'][k] for k in ['prompt_tokens','completion_tokens','total_tokens'])
            rawrows.append({'case_uid':r['case_uid'],'main_case_order':r['main_case_order'],
                'usage':r['usage'],'completion_status':r['completion_status'],
                'raw_completion_status':d.get('completion_status'),'llm_usage_summary':d['llm_usage_summary'],
                'algorithm_llm_calls':d.get('llm_calls'),'json_parse_exhausted_windows':d.get('json_parse_exhausted_windows'),
                'source_file':str(p),'source_sha256':r['source_sha256']})
        usage={k:sum(r['usage'].get(k,0) for r in rr) for k in ['prompt_tokens','completion_tokens','total_tokens','calls','failed_api_calls']}
        hist.append({'model':model,'case_n':len(rr),'usage':usage,'states':dict(Counter(r['completion_status'] for r in rr)),
            'json_parse_exhausted_windows':sum(r['json_parse_exhausted_windows'] or 0 for r in rawrows),
            'algorithm_llm_calls':sum(r['algorithm_llm_calls'] or 0 for r in rawrows),
            'reference_case_min_tokens':min(r['usage']['total_tokens'] for r in rr),
            'reference_case_max_tokens':max(r['usage']['total_tokens'] for r in rr),
            'raw_rows':rawrows})
    groups=[];means=[]
    for h in hist:
        model=h['model'];B=h['usage']['total_tokens']
        for method in ['lea','full-scc']:
            wavegroups=[]
            for wave in range(1,4):
                rr=[r for r in remote['rows'] if (r['model_key'],r['method'],r['wave'])==(model,method,wave)]
                assert len(rr)==80
                g={'model':model,'method':method,'wave':wave,**summarize(rr,B)}
                groups.append(g);wavegroups.append(g)
            rr=[r for r in remote['rows'] if (r['model_key'],r['method'])==(model,method)]
            summary=summarize(rr,3*B)
            means.append({'model':model,'method':method,'waves':3,'cases_per_wave':80,
                'reference_80_tokens':B,
                'mean_80_case_usage':{k:statistics.mean(g['usage'][k] for g in wavegroups) for k in wavegroups[0]['usage']},
                'mean_80_actual_to_reference_ratio':summary['actual_to_reference_ratio'],
                'mean_80_actual_minus_reference_tokens':summary['actual_minus_reference_tokens']/3,
                'all_240_case_audit':summary})
    snapshot=ROOT/'paper/latex/figures_equal_budget_20261012/internal_sources/three_model_summary.json'
    snap=json.loads(snapshot.read_text())['aggregate']
    for g in groups:
        check=next(c for c in snap['comparisons'] if (c['model'],c['method'])==(g['model'],g['method']))
        rr=[r for r in remote['rows'] if (r['model_key'],r['method'],r['wave'])==(g['model'],g['method'],g['wave'])]
        for metric in ['risk_all','risk_any','root_at_3']:
            assert abs(sum(r['metrics'].get(metric,0) for r in rr)/80-check['metrics'][metric]['wave_values'][g['wave']-1])<1e-12
    result={'scope':'CURRENT paper Fig.3/Table15; three local models; fixed historical SA80 versus mean of three baseline waves80 each',
            'comparison_rule':'Mean baseline prompt/completion/total per 80-case wave compared with single fixed 80-case SA reference. Never compare summed 240 baseline cases to 80 SA cases.',
            'snapshot_metrics_verified':True,'snapshot_path':str(snapshot),'snapshot_sha256':sha(snapshot),
            'reference_path':str(refpath),'reference_sha256':sha(refpath),
            'historical_sa':hist,'wave_groups':groups,'three_wave_means':means,
            'limitations':['Historical reference retry counters are not directly available; recorded API calls and exhausted windows are retained, algorithm call differences are not asserted as exact retries.',
                           'Historical source usage summaries are verified against immutable raw result hashes; independent per-request historical usage replay is not performed.',
                           'Baseline final usage includes candidate, retry, and selector/judge calls via one owner ledger; per-phase ledger check may be stored in the adjacent ledger audit.'],
            'remote':remote}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('SAVED',OUT)
    print('SA',json.dumps([{k:v for k,v in h.items() if k!='raw_rows'} for h in hist]))
    print('WAVES',json.dumps([{k:v for k,v in g.items() if k in ['model','method','wave','usage','actual_to_reference_ratio','states','over_cap_cases','cap_mismatch_cases']} for g in groups]))
    print('MEANS',json.dumps([{k:v for k,v in g.items() if k!='all_240_case_audit'} for g in means]))

if __name__=='__main__':main()
