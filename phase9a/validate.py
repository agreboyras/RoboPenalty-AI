"""Exact physical comparisons; deliberately exclude wall clocks and process IDs."""
from bootstrap import *
import argparse
import hashlib
import json
from phase5.benchmark import compare_physics

def read(p):return json.loads(p.read_text(encoding='utf-8'))

def compare(left,right):
    rows=[]
    for n in range(1,6):
        a=left/f'penalty_{n:02d}';b=right/f'penalty_{n:02d}'
        x,y=read(a/'physical.json'),read(b/'physical.json')
        compare_physics(x,y)
        for key in ('initial_state','agent','phase8b2'):
            assert x[key]==y[key],(n,key)
        assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state'],n
        for name in ('planning.json','posture.json','return.json','motor_monitor.json'):
            assert read(a/name)==read(b/name),(n,name)
        rows.append(dict(penalty=n,exact_initial_final_states=True,exact_trace_contacts_evaluation=True,
            exact_keeper_decisions_posture_return_motor_monitor=True))
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--left',type=Path,required=True);p.add_argument('--right',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--automatic',action='store_true');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output file inside phase9a required')
    rows=compare(a.left,a.right)
    if a.automatic:
        assert read(a.left/'match.json')['striker_statistics']==read(a.right/'match.json')['striker_statistics']
        for n in range(1,6):
            for name in ('decision_before_shot.json','feedback_after_shot.json'):
                x,y=read(a.left/f'penalty_{n:02d}'/name),read(a.right/f'penalty_{n:02d}'/name)
                if name=='feedback_after_shot.json':
                    # Execution timings are observations of different processes, not learning inputs.
                    for value in (x,y):
                        for key in ('wall_s','physics_call_wall_s'):value['record'].pop(key)
                assert x==y,(n,name)
    manifest=read(HERE/'results/protected_before.json')
    changed=[path for path,digest in manifest.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest]
    assert not changed,changed
    report=dict(passed=True,left=str(a.left),right=str(a.right),comparison='exact; no numerical tolerance',
        penalties=rows,automatic_decisions_learning_equal=a.automatic,protected_sources_unchanged=len(manifest))
    a.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
