"""Initial 5mm ball perturbations; paired free counterfactual per condition."""
from bootstrap import *
import argparse
import json
from phase8b2.experiment import BiasRuntime
from phase8b2.catalog import ShotCatalog
from phase8b3.runtime import components
from phase4a.evaluation import classify

def evaluate(actual,free):
    for key in ('qpos','qvel'):
        if actual['initial_state'][key]!=free['initial_state'][key]:raise AssertionError('Perturbed initial state differs')
    contact=actual['evaluation']['first_keeper_ball'];cut=contact['time_sim_s'] if contact else actual['simulated_s'];error=0.
    for a,b in zip(actual['trace'],free['trace']):
        if a['observation']['time_s']>=cut:break
        for key in ('ball_position_w','ball_velocity_w'):
            error=max(error,max(abs(x-y) for x,y in zip(a['observation'][key],b['observation'][key])))
    if error>1e-8:raise AssertionError('Perturbed shot differs before keeper contact')
    label=classify(actual,free)
    return {'save_with_contact_and_goal_counterfactual':'save'}.get(label,label),error

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--actions',nargs='+');p.add_argument('--deltas',nargs='+',type=float,default=[-.005,.005])
    p.add_argument('--compare-to',type=Path);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);catalog=ShotCatalog(PROJECT/'phase8b2/catalog_v1.json');rows=[]
    actions=a.actions or catalog.actions
    if not set(actions)<=set(catalog.actions) or any(abs(v)>.005 or not __import__('math').isfinite(v) for v in a.deltas):p.error('Only calibrated actions and initial perturbations up to 5mm')
    free=BiasRuntime();base=free.original_initialize
    for delta in a.deltas:
        def init(config,m,d,kick,rail,probe):
            base(config,m,d,kick,rail,probe);q=int(m.jnt_qposadr[m.body_jntadr[m.body('ball').id]])
            d.qpos[q+1]+=delta
        free.original_initialize=init
        runtimes={mode:components(catalog,mode,delta)[0]() for mode in ('historical','dynamic')}
        for action,(_,bias) in catalog.mapping.items():
            if action not in actions:continue
            folder=a.output/f'{delta:+.3f}_{action}';folder.mkdir()
            probe=free.trial(bias,folder/'free.json')
            for mode,runtime in runtimes.items():
                target=folder/mode;target.mkdir()
                error_text=None
                try:r,_,_=runtime.execute('long','agent',target/'physical.json',lambda o:action,lambda:None)
                except RuntimeError as exc:
                    error_text=str(exc)
                    if not (target/'physical.json').exists():raise
                    r=json.loads((target/'physical.json').read_text())
                body=json.loads((target/'posture.json').read_text())
                outcome,error=evaluate(r,probe)
                if a.compare_to:
                    from phase5.benchmark import compare_physics
                    old_folder=a.compare_to/f'{delta:+.3f}_{action}'
                    compare_physics(json.loads((old_folder/mode/'physical.json').read_text()),r)
                    compare_physics(json.loads((old_folder/'free.json').read_text()),probe)
                    assert json.loads((old_folder/mode/'posture.json').read_text())==body
                row=dict(delta_y_m=delta,action=action,mode=mode,outcome=outcome,physical_passed=r['passed'],
                    physical_failures=r['failures'],posture_passed=body['passed'],posture_failures=body['failures'],
                    free_goal_crossing=probe['evaluation']['goal_crossing_measured'],
                    actual_goal_crossing=r['evaluation']['goal_crossing_measured'],
                    contact=r['evaluation']['first_keeper_ball'],foot=r['evaluation']['first_foot_ball'],
                    fall=r['evaluation']['shooter_fall_time_s'],max_joint_speed=body['max_joint_speed_rad_s'],prefix_error=error,
                    exception=error_text)
                rows.append(row);(a.output/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
                print(json.dumps(row),flush=True)
                if not body['passed'] or any(r['engine_warnings']):raise RuntimeError('Keeper robustness failure; stop subsequent stages')
if __name__=='__main__':main()
