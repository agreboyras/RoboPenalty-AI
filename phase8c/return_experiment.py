from bootstrap import *
import argparse
import json
from phase8b2.catalog import ShotCatalog
from phase8c.runtime import components

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);catalog=ShotCatalog(PROJECT/'phase8b2/catalog_v1.json');summary=[]
    for posture in ('historical','dynamic'):
        for correction in (False,True):
            Runtime,_=components(catalog,posture,.005,correction);runtime=Runtime()
            folder=a.output/f'{posture}_{correction}';folder.mkdir();exception=None
            try:r,_,_=runtime.execute('long','agent',folder/'physical.json',lambda o:'center',lambda:None)
            except RuntimeError as ex:
                exception=str(ex);r=json.loads((folder/'physical.json').read_text())
            rows=json.loads((folder/'return.json').read_text())['rows']
            if not correction:
                old=json.loads((PROJECT/'phase8b3/results/ball_perturbations/+0.005_center'/posture/'physical.json').read_text())
                from phase5.benchmark import compare_physics
                compare_physics(old,r)
            else:
                reference=json.loads((a.output/f'{posture}_False/return.json').read_text())['rows']
                for x,y in zip(rows,reference):
                    if x['state']=='DONE' or y['state']=='DONE':break
                    for key in ('state','executed_command_m','q_m','v_mps','reference_q_m','reference_v_mps'):assert x[key]==y[key],key
                if not r['passed']:raise RuntimeError('Return-only candidate failed original thresholds')
            summary.append(dict(posture=posture,correction=correction,passed=r['passed'],failures=r['failures'],
                final_q_m=r['rail']['final_q_m'],first_DONE=next((v for v in rows if v['state']=='DONE'),None),last=rows[-1],exception=exception))
            (a.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            print(json.dumps(summary[-1]),flush=True)
if __name__=='__main__':main()
