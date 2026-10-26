"""Offline comparison; never imported by the live planners."""
import argparse
import json
from bootstrap import *
from phase8b1.metrics import summarize
from phase5.benchmark import compare_physics

def main():
    p=argparse.ArgumentParser();p.add_argument('--shots',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New phase8b1 report required')
    original=json.loads((a.shots/'summary.json').read_text(encoding='utf-8'));reports=[]
    for old in original:
        repeat=2 if old['reproducible_comparison'] else 1
        folder=a.shots/f'{old["variant"]}_{old["action"]}_{repeat:02d}'
        physical=json.loads((folder/'physical.json').read_text(encoding='utf-8'))
        if repeat==2:
            first=json.loads((a.shots/f'{old["variant"]}_{old["action"]}_01/physical.json').read_text(encoding='utf-8'))
            assert physical['phase5_state']['final_integration_state']==first['phase5_state']['final_integration_state']
            assert physical['phase5_state']['final_integration_sha256']==first['phase5_state']['final_integration_sha256']
        r=summarize(folder,physical,old['outcome'],old['variant'],old['action'])
        rows=json.loads((folder/'planning.json').read_text(encoding='utf-8'))['decision_rows']
        def reversals(values):return sum(x!=y for x,y in zip(values,values[1:]))
        r.update(repeat=repeat,reproducible_comparison=old['reproducible_comparison'],
                 full_final_state_repeated_exactly=repeat==2,
                 velocity_reversals_total=reversals([1 if row['actual_v_mps']>0 else -1 for row in rows if abs(row['actual_v_mps'])>.02]),
                 velocity_reversals_tracking=reversals([1 if row['actual_v_mps']>0 else -1 for row in rows if row['state']=='TRACKING' and abs(row['actual_v_mps'])>.02]))
        assert r['passed'] and r['shooter_fall_time_s'] is None and not any(r['warnings'])
        assert r['peak_speed_mps']<=.4 and r['peak_acceleration_mps2']<=8 and r['peak_force_n']<=120
        assert r['max_abs_q_m']<=.752 and r['max_command_before_critical_m']<=.65
        reports.append(r)
    matches={}
    for variant in 'ABC':
        path=HERE/f'results/match_{variant}'
        match=json.loads((path/'match_001/match.json').read_text(encoding='utf-8'))
        session=json.loads((path/'session.json').read_text(encoding='utf-8'))
        assert session['physics_steps']==35000 and session['failure'] is None
        assert match['phase']=='FINISHED' and len(match['scoreboard']['history'])==5
        for n,record in enumerate(match['scoreboard']['history'],1):
            x=json.loads((path/f'match_001/penalty_{n:02d}/physical.json').read_text(encoding='utf-8'))
            y=json.loads((a.shots/f'{variant}_{record["action"]}_01/physical.json').read_text(encoding='utf-8'))
            compare_physics(x,y)
            assert x['phase5_state']['final_integration_state']==y['phase5_state']['final_integration_state']
        matches[variant]=dict(scoreboard=match['scoreboard'],wall_s=session['script_wall_s'],steps=session['physics_steps'],
                              actionwise_exact_to_isolated_trials=True,runtime=session['runtime'])
    a.output.write_text(json.dumps(dict(trials=reports,matches=matches),indent=2),encoding='utf-8')
    print('PASS limits, reproducibility and actionwise full-match equivalence')

if __name__=='__main__':main()
