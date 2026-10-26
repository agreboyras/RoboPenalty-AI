"""Exact paired physics and match comparisons; no new numerical tolerances."""
from bootstrap import *
import argparse
import json
from phase5.benchmark import compare_physics
from phase7b.validate import compare as compare_matches

def compare_pair(a,b):
    x,y=[json.loads((folder/'physical.json').read_text(encoding='utf-8')) for folder in (a,b)]
    compare_physics(x,y)
    for key in ('initial_state','agent','engine_warnings','failures','passed'):
        assert x[key]==y[key],key
    assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state']
    assert x['phase8b2']==y['phase8b2']
    assert json.loads((a/'planning.json').read_text(encoding='utf-8'))==json.loads((b/'planning.json').read_text(encoding='utf-8'))
    return dict(pair=[str(a),str(b)],exact_trajectory_contacts_agent_commands_initial_final_state=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--pairs',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    if a.pairs:
        rows=[]
        for first in sorted(a.pairs.glob('*_01')):
            second=first.with_name(first.name[:-2]+'02');rows.append(compare_pair(first,second))
        if not rows:raise AssertionError('No pairs found')
        result=dict(passed=True,pairs=rows)
    else:
        result=compare_matches(a.reference,a.candidate)
        left=a.reference/'match_001';right=a.candidate/'match_001'
        if not left.exists():left=a.reference
        if not right.exists():right=a.candidate
        extra_count=0
        for x in sorted(left.glob('penalty_*')):
            l=json.loads((x/'physical.json').read_text(encoding='utf-8'));r=json.loads((right/x.name/'physical.json').read_text(encoding='utf-8'))
            if 'phase8b2' in l or 'phase8b2' in r:
                assert l['phase8b2']==r['phase8b2'];extra_count+=1
            if (x/'planning.json').exists():
                assert json.loads((x/'planning.json').read_text(encoding='utf-8'))==json.loads((right/x.name/'planning.json').read_text(encoding='utf-8'))
        result['extra_exact_500hz_ball_and_foot_contact_telemetry_episodes']=extra_count
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print('PASS exact comparison',flush=True)
if __name__=='__main__':main()
