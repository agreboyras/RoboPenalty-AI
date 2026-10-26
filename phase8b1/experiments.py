"""Gated experiments using original physical runners and unchanged limits."""
import argparse
from contextlib import redirect_stdout
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from bootstrap import *
from phase8b1.integrity import protected_sources

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['servo','shots'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--variants',nargs='+',choices=['A','B','C'],default=['A','B','C'])
    p.add_argument('--actions',nargs='+',choices=['left','center','right'],default=['left','center','right'])
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or not out.is_relative_to(HERE):raise ValueError('New phase8b1 output required')
    out.mkdir(parents=True);before=protected_sources()
    try:
        if a.stage=='servo':
            e=load(PROJECT/'phase3a/experiment.py','eight_servo')
            for case in ('left','right','return'):
                with (out/f'{case}.log').open('w',encoding='utf-8') as log,redirect_stdout(log):
                    status=e.run(SimpleNamespace(case=case,duration=14.,viewer=False,unpaced=True,output=out/f'{case}.json'))
                if status:raise RuntimeError(f'Unsafe servo test: {case}')
                print(case,'PASS',flush=True)
        else:
            from runtime import SimulationRuntime
            from phase8b1.runtime_adapter import install
            from phase8b1.metrics import summarize
            reference={a:json.loads((PROJECT/f'phase7d/results/integrated_viewer/match_001/penalty_{i:02d}/physical.json').read_text(encoding='utf-8'))
                       for a,i in [('left',1),('right',2),('center',3)]}
            reports=[];first={}
            for variant in a.variants:
                runtime=install(SimulationRuntime(),variant)
                for n in range(a.repeats):
                    for action in a.actions:
                        folder=out/f'{variant}_{action}_{n+1:02d}';folder.mkdir()
                        result,_,wall=runtime.execute('long','agent',folder/'physical.json',lambda obs:action,lambda:None)
                        outcome,_=runtime.evaluate(result,'long',action)
                        report=summarize(folder,result,outcome,variant,action)
                        report['wall_s']=wall
                        if variant=='A':
                            for key in ('initial_state','evaluation','rail','trace','agent','configuration'):
                                assert result[key]==reference[action][key],key
                            assert result['phase5_state']['final_integration_state']==reference[action]['phase5_state']['final_integration_state']
                            report['exact_7d_reference']=True
                        key=(variant,action)
                        fingerprint={k:result[k] for k in ('initial_state','evaluation','rail','trace','agent')}
                        fingerprint['final_integration_state']=result['phase5_state']['final_integration_state']
                        if key in first:assert fingerprint==first[key],'Nonreproducible physical trial'
                        else:first[key]=fingerprint
                        report['reproducible_comparison']=n>0
                        reports.append(report)
                        (out/'summary.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
                        print(variant,action,n+1,outcome,report['useful_q_m'],flush=True)
    finally:
        after=protected_sources();changed=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
        (out/'protected_sources.json').write_text(json.dumps(dict(checked=len(before),changed=changed),indent=2),encoding='utf-8')
        if changed:raise RuntimeError(changed)

if __name__=='__main__':main()
