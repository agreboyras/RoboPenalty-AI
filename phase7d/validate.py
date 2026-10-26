"""Exact prior-phase physical/learning comparator plus live scoreboard checks."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from phase7b.validate import compare

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New phase7d report required')
    report=compare(a.reference,a.candidate)
    session=json.loads((a.candidate/'session.json').read_text(encoding='utf-8'))
    v=session['presentation']['phase7d'];match=json.loads((a.candidate/'match_001/match.json').read_text(encoding='utf-8'))
    score=match['scoreboard'];assert v['screen_state']==[score['goals'],score['saves'],5,5]
    for e in v['screen_events']:
        s=e['status'];assert e['screen']==[s.get('goals',0),s.get('saves',0),s.get('penalty',0),s.get('total',5)]
        assert e['state_unchanged']
    assert all(p['full_integration_state_unchanged'] for p in session['control_pauses'])
    report.update(screen_matches_all_status_events=True,control_pauses=session['control_pauses'],phase7d=v)
    a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS exact physics, traces, contacts, agents, learning, scoreboard and pauses')

if __name__=='__main__':main()
