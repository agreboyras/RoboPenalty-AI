"""Validate controlled early termination against first completed reference shot."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from phase7b.validate import compare_physics,learning_payload

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
    read=lambda path:json.loads(path.read_text(encoding='utf-8'))
    candidate=a.candidate.resolve()
    if not candidate.is_relative_to(HERE):raise ValueError('phase7d candidate required')
    session=read(candidate/'session.json');match=read(candidate/'match_001/match.json')
    assert len(match['scoreboard']['history'])==1
    assert any(c.get('intent')=='stop' and c['accepted'] for c in session['commands'])
    assert session['physics_steps']==7000 and session['failure'] is None
    assert session['presentation']['viewer_closed'] and session['presentation']['viewer_render_thread_joined']
    x=read(HERE/'results/integrated_headless/match_001/penalty_01/physical.json')
    y=read(candidate/'match_001/penalty_01/physical.json');compare_physics(x,y)
    assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state']
    assert not read(candidate/'protected_sources.json')['changed']
    report=dict(passed=True,completed_physical_penalties=1,physics_steps=7000,
                exact_first_episode=True,controlled_stop=True,closed_and_joined=True)
    (candidate/'stop_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS controlled stop after exact complete first episode; viewer closed')

if __name__=='__main__':main()
