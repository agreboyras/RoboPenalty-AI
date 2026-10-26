from bootstrap import *
import argparse
import json
from phase8b2.catalog import ShotCatalog
from phase8b3.runtime import components
from phase8b2.compare import metrics
from phase5.benchmark import compare_physics

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--modes',nargs='+',choices=['historical','dynamic'],default=['historical','dynamic']);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);catalog=ShotCatalog(PROJECT/'phase8b2/catalog_v1.json');rows=[]
    for mode in a.modes:
        Runtime,_=components(catalog,mode);runtime=Runtime()
        for action in catalog.actions:
            first=None
            for n in range(a.repeats):
                folder=a.output/f'{mode}_{action}_{n+1:02d}';folder.mkdir()
                r,_,wall=runtime.execute('long','agent',folder/'physical.json',lambda o:action,lambda:None)
                outcome,error=runtime.evaluate(r,'long',action);body=json.loads((folder/'posture.json').read_text())
                row=metrics(r,folder,outcome,mode,action,error);row.update(posture={k:v for k,v in body.items() if k!='rows'},repeat=n+1,wall_s=wall)
                if first is not None:
                    compare_physics(first,r)
                    assert first['phase5_state']['final_integration_state']==r['phase5_state']['final_integration_state']
                    assert json.loads((a.output/f'{mode}_{action}_01/posture.json').read_text())==body
                first=r
                if mode=='historical':
                    old=json.loads((PROJECT/'phase8b2/results/agents'/f'B_{action}_01/physical.json').read_text())
                    compare_physics(old,r)
                    assert old['phase5_state']['final_integration_state']==r['phase5_state']['final_integration_state']
                rows.append(row);(a.output/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
                print(json.dumps(dict(mode=mode,action=action,repeat=n+1,result=outcome,body_passed=body['passed'],joint_motion=body['max_joint_excursion_rad'],self_contacts=body['self_contact_pairs'])),flush=True)
if __name__=='__main__':main()
