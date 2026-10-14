#!/usr/bin/env python3
"""Read compact progress without contacting a model or starting a task."""
import json
from cluster_runner import ROOT, read
from cluster_supervisor import collect_results


def main():
    path=ROOT/'execution/status.json'
    state=read(path) if path.exists() else {'status':'not_started'}
    compact={k:v for k,v in state.items() if k!='workers'}
    compact.update(collect_results())
    compact['failed_workers']=[{k:e.get(k) for k in ('name','pid','exit_code')}
                                for e in state.get('workers',[]) if e.get('exit_code') not in (None,0)]
    print(json.dumps(compact,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
