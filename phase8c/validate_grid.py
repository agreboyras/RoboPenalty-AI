"""Both postures, exact same initial grid, corrected return and existing scoring."""
from bootstrap import *
import argparse
import gc
import json
from phase8c.catalog import Catalog
from phase8c.runtime import components
from phase8b3.robustness import evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--catalog',type=Path,default=HERE/'catalog_v1.json');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);catalog=Catalog(a.catalog);summary=[]
    for delta in (-.005,-.002,-.001,0.,.001,.002,.005):
        for posture in ('historical','dynamic'):
            Runtime,_=components(catalog,posture,delta);runtime=Runtime()
            for action,entry in catalog.entries.items():
                folder=a.output/f'dy{delta:+.3f}_{posture}_{action}';folder.mkdir()
                condition=next(c for c in entry['grid'] if c['delta_y_m']==delta)
                free=json.loads((catalog.path.parent/condition['source']).read_text())
                r,_,wall=runtime.execute('long','agent',folder/'physical.json',lambda o:action,lambda:None)
                result,error=evaluate(r,free)
                if result not in ('goal','save','miss'):raise RuntimeError(f'Unresolved score {result}')
                body=json.loads((folder/'posture.json').read_text());ret=json.loads((folder/'return.json').read_text())
                if abs(ret['final_physical']['v_mps'])>=.02:raise RuntimeError('Final rail speed not settled')
                tail=[row for row in body['rows'] if row['time_s']>=12]
                import numpy as np
                oscillation=float(np.ptp(np.array([row['actual_rad'] for row in tail]),axis=0).max())
                row=dict(delta_y_m=delta,posture=posture,action=action,result=result,passed=r['passed'],
                    body_passed=body['passed'],body_failures=body['failures'],rail=r['rail'],
                    final_physical=ret['final_physical'],contact=r['evaluation']['first_keeper_ball'],
                    foot=r['evaluation']['first_foot_ball'],fall=r['evaluation']['shooter_fall_time_s'],
                    keeper_tilt_deg=r['evaluation']['keeper_max_tilt_deg'],max_joint_speed=body['max_joint_speed_rad_s'],
                    max_actual_joint_torque_nm=body['max_actual_joint_torque_nm'],max_tracking_error_rad=body['max_tracking_error_rad'],
                    self_contacts=body['self_contact_pairs'],last_two_seconds_joint_p2p_rad=oscillation,
                    prefix_error=error,wall_s=wall,warnings=r['engine_warnings'])
                summary.append(row);(a.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
                print(json.dumps(dict(dy_mm=delta*1000,posture=posture,action=action,result=result,final_q=row['final_physical']['q_m'],final_v=row['final_physical']['v_mps'],body_passed=body['passed'])),flush=True)
            del runtime;gc.collect()
if __name__=='__main__':main()
