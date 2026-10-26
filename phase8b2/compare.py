"""Paired physical comparisons; free calibration outcomes remain offline."""
from bootstrap import *
import argparse
import json
from phase8b2.catalog import ShotCatalog
from phase8b2.runtime import components
from phase8b1.runtime_adapter import install
from phase8b2.integrity import protected_sources

def metrics(r,folder,label,variant,action,error):
    ev=r['evaluation'];cross=ev['approach_crossing_measured'];contact=ev['first_keeper_ball']
    critical=cross['time_sim_s'] if cross else contact['time_sim_s'] if contact else None
    planning=json.loads((folder/'planning.json').read_text(encoding='utf-8'))
    rows=planning['decision_rows'];before=[row for row in rows if critical is not None and row['time_s']<=critical]
    surfaces=planning['physical_probe'].get('surface_samples',[])
    goal=ev['goal_crossing_measured']
    surfaces=[s for s in surfaces if not goal or s['time_s']<=goal['time_sim_s']]
    return dict(variant=variant,action=action,outcome=label,passed=r['passed'],
        plane4=cross,plane5=goal,agent=r['agent'],rail=r['rail'],contact=contact,
        maximum_command_before_critical_m=max((abs(row['servo_command_m']) for row in before),default=0.),
        actual_q_at_critical_m=cross['rail_q_m'] if cross else contact['rail_q_m'] if contact else None,
        minimum_surface_before_goal_sampled_m=min((s['distance_m'] for s in surfaces),default=None),
        surface_sample_rate_hz=50,ball_prefix_error_m=error,foot_force_n=ev['foot_peak_force_n'],
        fall=ev['shooter_fall_time_s'],max_shooter_tilt_deg=ev['shooter_max_tilt_deg'],
        max_keeper_tilt_deg=ev['keeper_max_tilt_deg'],warnings=r['engine_warnings'],
        final_sha256=r['phase5_state']['final_integration_sha256'],wall_s=r['timing']['loop_wall_s'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--variants',nargs='+',choices=['fixed','A','B'],default=['fixed','A','B'])
    p.add_argument('--repeats',type=int,default=2);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE) or a.repeats<1:p.error('New output inside phase8b2 and positive repeats required')
    before=protected_sources();a.output.mkdir(parents=True)
    catalog=ShotCatalog(a.catalog);Runtime,_=components(catalog);summaries=[]
    for variant in a.variants:
        runtime=install(Runtime(),'A' if variant=='fixed' else variant)
        for action in catalog.actions:
            for n in range(a.repeats):
                folder=a.output/f'{variant}_{action}_{n+1:02d}';folder.mkdir()
                r,_,_=runtime.execute('long','fixed' if variant=='fixed' else 'agent',folder/'physical.json',lambda o:action,lambda:None)
                label,error=runtime.evaluate(r,'long',action)
                row=metrics(r,folder,label,variant,action,error);row['repeat']=n+1;summaries.append(row)
                (a.output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')
                print(json.dumps(dict(variant=variant,action=action,repeat=n+1,outcome=label,q=row['actual_q_at_critical_m'],gap=row['minimum_surface_before_goal_sampled_m'])),flush=True)
                if n and row['final_sha256']!=next(s['final_sha256'] for s in summaries if s['variant']==variant and s['action']==action):
                    raise AssertionError('Nonreproducible candidate')
    after=protected_sources();changed=[k for k,v in before.items() if after.get(k)!=v]
    (a.output/'integrity.json').write_text(json.dumps(dict(checked=len(before),changed=changed),indent=2),encoding='utf-8')
    if changed:raise AssertionError(changed)
if __name__=='__main__':main()
