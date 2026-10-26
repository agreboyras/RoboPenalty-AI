"""Reuse the exact physical and learning comparison established in 7B."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from phase7b.validate import compare
from phase7c.integrity import save

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New report inside phase7c required')
    result=compare(a.reference,a.candidate)
    session=json.loads((a.candidate/'session.json').read_text(encoding='utf-8'))
    visual=session['presentation']['phase7c']
    if visual['stage']>=3 and visual['lod']!='none':
        match=json.loads((a.candidate/'match_001/match.json').read_text(encoding='utf-8'))
        score=match['scoreboard']
        assert visual['screen_state']==[score['goals'],score['saves'],match['config']['penalties'],match['config']['penalties']], 'Screen disagrees with actual match'
        result['screen_matches_orchestrator']=True
    result['phase7c']=visual
    save(a.output,result)
    print('PASS: exact physical states, recorded contacts, trajectories, decisions and learning')

if __name__=='__main__':main()
