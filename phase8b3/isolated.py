"""Keeper-only assessment in the unchanged shared world; inactive shooter parked away."""
from bootstrap import *
import argparse
import json
import numpy as np
import mujoco
import yaml
from types import SimpleNamespace
from lateral_scene import build_scene,Limits
from lateral_control import LateralControl
from observations import Observation
from phase8b1.planners import InterceptionPlanner
from phase8b3.posture import PosturePD

def run(out,mode,scenario,initial_joint_delta=0.):
    limits=Limits();m,d,sh,gk,rail=build_scene(PROJECT.parent/'RoboNaldo_Deploy',PROJECT.parent/'unitree_mujoco',limits)
    base=np.array([.25 if 'left_shoulder_roll' in m.joint(int(j)).name else -.25 if 'right_shoulder_roll' in m.joint(int(j)).name else .3 if 'elbow' in m.joint(int(j)).name else 0. for j in gk.joints])
    d.qpos[gk.qpos]=base
    d.qpos[gk.qpos[15]]+=initial_joint_delta
    # Unused shooter and ball are relocated only before integration. No ball launches.
    sj=m.body_jntadr[sh.pelvis];d.qpos[m.jnt_qposadr[sj]]=-20
    bj=m.body_jntadr[m.body('ball').id];d.qpos[m.jnt_qposadr[bj]:m.jnt_qposadr[bj]+3]=[-15,10,.115]
    mujoco.mj_forward(m,d)
    caps=np.array(yaml.safe_load((PROJECT.parent/'RoboNaldo_Deploy/deploy_mujoco/config/mujoco_freekick.yaml').read_text())['tau_limit'])
    servo=LateralControl(limits,rail);pd=PosturePD(m,gk,rail,mode)
    def snapshot():return dict(reference_q=servo.position,reference_v=servo.velocity,reference_a=servo.acceleration,mass=rail.carried_mass,damping=rail.damping)
    planner=InterceptionPlanner(limits,'B',snapshot)
    maxrailv=0.;footload=0.;capture_states={}
    for step in range(5000):
        t=float(d.time);side=1 if scenario in ('left','lateral') else -1
        if step%10==0:
            obs=Observation(t,(-1+3*(t-2),side*.55,.115),(3.,0.,0.) if 2<=t<5 else (0.,0.,0.),float(d.qpos[rail.qpos]),float(d.qvel[rail.dof]))
            if scenario=='lateral':decision=planner.step(obs);servo.select(decision.selected_target_m)
            else:
                active=2<=t<5 and scenario!='wait'
                prediction=dict(valid=active,y_w=side*.55 if active else None)
                decision=SimpleNamespace(state='TRACKING' if active else 'RETURNING' if t>=5 else 'WAITING',prediction=prediction)
            pd.notify(decision,obs)
        servo.advance_reference(m.opt.timestep)
        d.ctrl[gk.actuators]=pd.command(d,base,caps)
        d.ctrl[rail.actuator]=servo.force(float(d.qpos[rail.qpos]),float(d.qvel[rail.dof]))
        mujoco.mj_step(m,d);maxrailv=max(maxrailv,abs(float(d.qvel[rail.dof])))
        for stage,when in [('wait',1.8),('reaction',4.),('recovery',5.8),('recovered',9.8)]:
            if stage not in capture_states and d.time>=when:capture_states[stage]=dict(time_s=float(d.time),qpos=d.qpos.tolist(),qvel=d.qvel.tolist(),ctrl=d.ctrl.tolist())
    result=pd.summary();result.update(scenario=scenario,initial_shoulder_pitch_delta_rad=initial_joint_delta,isolated_stimulus='synthetic current observations/scheduled transitions; not a physical shot',
        inactive_shooter_note='parked at X=-20, unactuated; its settling is excluded from keeper stability',
        rail_max_speed_mps=maxrailv,engine_warnings=[int(w.number) for w in d.warning],snapshots=capture_states)
    if any(result['engine_warnings']):result['passed']=False;result['failures'].append('engine_warning')
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('mode','scenario','passed','failures','max_joint_speed_rad_s','max_tracking_error_rad','self_contact_pairs','floor_contact_geoms','max_pelvis_constraint_error_m')}),flush=True)
    return result['passed']

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--perturb',action='store_true');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New phase8b3 output required')
    a.output.mkdir(parents=True)
    if a.perturb:
        for delta in (-.01,.01):
            if not run(a.output/f'joint_{delta:+.2f}.json','dynamic','lateral',delta):return 2
        return 0
    for mode in ('historical','dynamic'):
        for scenario in ('wait','left','right','lateral'):
            if not run(a.output/f'{mode}_{scenario}.json',mode,scenario):return 2
    return 0
if __name__=='__main__':sys.exit(main())
