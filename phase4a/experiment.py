"""Phase 4A physical scenario runner. Reuses owned previous phases unchanged."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

START = time.perf_counter()
sys.dont_write_bytecode = True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
HOME = Path(__file__).resolve().parent
sys.path.insert(0, str(HOME.parents[0] / 'phase3a'))
sys.path.insert(0, str(HOME.parents[0] / 'phase3b'))
from scenarios import SCENARIOS, initialize

import mujoco
import numpy as np
import yaml

from lateral_scene import build_scene, Limits
from lateral_control import LateralControl
from freekick_adapter import FreeKickAdapter
from observations import ObservationReader
from predictor import predict
from agent import GoalkeeperAgent


def tilt(quat):
    return math.degrees(math.acos(float(np.clip(1 - 2*(quat[1]**2 + quat[2]**2), -1, 1))))


def run(args):
    project = HOME.parents[0]
    output = Path(args.output).resolve()
    if not output.is_relative_to(project) or output.exists():
        raise ValueError('Output must be new and inside RoboPenalty')
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = project.parent
    deploy, unitree = workspace / 'RoboNaldo_Deploy', workspace / 'unitree_mujoco'
    external = json.loads((project/'phase2/results/benchmark/single_01.json').read_text(encoding='utf-8'))['external_inputs']['files_sha256']
    old_sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for phase in ['phase2','phase3a','phase3b'] for p in (project/phase).glob('*.py')}
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in external.items()):
        raise AssertionError('External dependencies changed since phase 2')
    limits = Limits()
    t = time.perf_counter()
    model, data, shooter, keeper, rail = build_scene(deploy, unitree, limits)
    build_s = time.perf_counter()-t
    with (deploy/'deploy_mujoco/config/mujoco_freekick.yaml').open() as f:
        torque_limits = np.asarray(yaml.safe_load(f)['tau_limit'])
    t = time.perf_counter()
    kick = FreeKickAdapter(deploy, model, shooter)
    load_s = time.perf_counter()-t
    posture = np.zeros(29)
    for n,j in enumerate(keeper.joints):
        name = model.joint(int(j)).name
        if 'shoulder_roll' in name:
            posture[n] = 0.25 if 'left_' in name else -0.25
        elif 'elbow' in name:
            posture[n] = 0.30
    data.qpos[keeper.qpos] = posture  # Initial pose only, before physics starts.
    scenario = SCENARIOS[args.scenario]
    initialize(scenario, model, data, kick, rail, args.mode == 'probe')
    mujoco.mj_forward(model, data)
    initial_hash = hashlib.sha256(data.qpos.tobytes()+data.qvel.tobytes()+model.body_pos.tobytes()).hexdigest()
    initial_state = {'qpos':data.qpos.tolist(), 'qvel':data.qvel.tolist(),
                     'keeper_origin':model.body_pos[rail.carriage].tolist()}
    control = LateralControl(limits, rail)
    reader = ObservationReader(model, rail)
    agent = GoalkeeperAgent(limits) if args.mode == 'agent' else None
    ball = model.body('ball').id
    ball_geom, floor = model.geom('ball_geom').id, model.geom('floor').id
    ball0 = data.qpos[reader.ball_q:reader.ball_q+3].copy()
    previous_ball = ball0.copy()
    previous_q, previous_v = float(data.qpos[rail.qpos]), float(data.qvel[rail.dof])
    trace = []
    first_foot = first_keeper = first_movement = first_forward_observed = None
    approach_crossing = goal_crossing = first_fall = None
    last_decision = None
    decision_events = []
    foot_peak_force = 0.0
    peak_ball_speed = 0.0
    first_foot_velocity = None
    contact_peak = qmax = max_v = max_a = max_ref_v = max_ref_a = max_force = 0.0
    qmin = 0.0
    max_torso = max_keeper_torso = 0.0
    base_quat = data.xquat[keeper.pelvis].copy()
    base_z = float(data.xpos[keeper.pelvis,2])
    max_base_error = max_base_height_error = 0.0
    nonfoot_floor = robot_collision = False
    # Broad-phase projected collision bounds at the ball's initial height.
    # This is an envelope, not proof of coverage (gaps and shape corners remain).
    coverage = []
    for geom in keeper.geoms:
        if not (int(model.geom_contype[geom]) & int(model.geom_conaffinity[ball_geom]) or
                int(model.geom_contype[ball_geom]) & int(model.geom_conaffinity[geom])):
            continue
        rotation = data.geom_xmat[geom].reshape(3,3)
        center = data.geom_xpos[geom] + rotation @ model.geom_aabb[geom,:3]
        extent = np.abs(rotation) @ model.geom_aabb[geom,3:]
        radius = .115
        if abs(center[0]-reader.plane_x)<=extent[0]+radius and abs(center[2]-.115)<=extent[2]+radius:
            coverage.append({'geom':model.geom(geom).name,'y_min':float(center[1]-extent[1]),'y_max':float(center[1]+extent[1])})
    loop_start = time.perf_counter()
    for step in range(round(args.duration / model.opt.timestep)):
        sim_t = float(data.time)
        if step % 10 == 0:
            observation = reader.read(data)
            prediction = predict(observation)
            if observation.ball_velocity_w[0] >= 0.8 and first_forward_observed is None:
                first_forward_observed = sim_t
            if agent:
                decision = agent.step(observation)
                control.select(decision.selected_target_m)
                if last_decision is None or decision.state != last_decision.state or decision.command_changed:
                    decision_events.append(asdict(decision))
                last_decision = decision
            if args.mode in ('capacity_left','capacity_right'):
                control.select((0.65 if args.mode=='capacity_left' else -0.65) if 4.18 <= sim_t < 8.0 else 0.0)
            trace.append({'observation': asdict(observation),
                          'prediction': asdict(prediction),
                          'decision': asdict(last_decision) if last_decision else None,
                          'command_m': control.goal})
        control.advance_reference(model.opt.timestep)
        kick.command_before_step(step * model.opt.timestep)
        data.ctrl[shooter.actuators] = kick.torque(data, torque_limits)
        data.ctrl[keeper.actuators] = np.clip(70*(posture-data.qpos[keeper.qpos])-5*data.qvel[keeper.dofs], -torque_limits, torque_limits)
        data.ctrl[rail.actuator] = control.force(float(data.qpos[rail.qpos]), float(data.qvel[rail.dof]))
        max_force = max(max_force, abs(float(data.ctrl[rail.actuator])))
        mujoco.mj_step(model,data)
        now = float(data.time)
        q,v = float(data.qpos[rail.qpos]),float(data.qvel[rail.dof])
        max_v = max(max_v,abs(v))
        max_a = max(max_a,abs((v-previous_v)/model.opt.timestep))
        qmin,qmax = min(qmin,q),max(qmax,q)
        max_ref_v,max_ref_a = max(max_ref_v,abs(control.velocity)),max(max_ref_a,abs(control.acceleration))
        if agent and agent.detection_time is not None and first_movement is None and abs(q)>0.003 and abs(v)>0.01:
            first_movement = now
        ball_position = data.qpos[reader.ball_q:reader.ball_q+3].copy()
        ball_velocity = data.qvel[reader.ball_v:reader.ball_v+3].copy()
        peak_ball_speed = max(peak_ball_speed, float(np.linalg.norm(ball_velocity)))
        def crossing(plane):
            if previous_ball[0]<plane<=ball_position[0]:
                alpha = (plane-previous_ball[0])/(ball_position[0]-previous_ball[0])
                position = previous_ball+alpha*(ball_position-previous_ball)
                rail_at_cross = previous_q+alpha*(q-previous_q)
                return {'time_sim_s': sim_t+alpha*model.opt.timestep,
                        'position_w': position.tolist(), 'rail_q_m': rail_at_cross,
                        'command_m': control.goal,
                        'keeper_center_y_w': reader.origin_y-rail_at_cross,
                        'ball_velocity_w':ball_velocity.tolist(),
                        'center_alignment_error_m': abs(position[1]-reader.origin_y+rail_at_cross)}
        if approach_crossing is None:
            approach_crossing = crossing(reader.plane_x)
        if goal_crossing is None:
            event = crossing(5.0)
            if event:
                event['inside'] = bool(abs(event['position_w'][1])<=1.5 and 0<=event['position_w'][2]<=1.8)
                goal_crossing = event
        for n in range(data.ncon):
            c = data.contact[n]
            a,b = int(c.geom1),int(c.geom2)
            other = b if a==ball_geom else a if b==ball_geom else None
            if other in shooter.foot_geoms:
                foot_force = np.zeros(6)
                mujoco.mj_contactForce(model,data,n,foot_force)
                foot_peak_force = max(foot_peak_force,float(foot_force[0]))
            if other in shooter.foot_geoms and first_foot is None:
                first_foot_velocity = ball_velocity.tolist()
                first_foot = {'time_sim_s':now,'legacy_step_label_s':step*model.opt.timestep,'geom':model.geom(other).name}
            if other in keeper.geoms:
                force = np.zeros(6)
                mujoco.mj_contactForce(model,data,n,force)
                contact_peak = max(contact_peak,float(force[0]))
                if first_keeper is None and force[0]>0:
                    first_keeper = {'time_sim_s':now,'geom':model.geom(other).name,
                                    'normal_force_n':float(force[0]), 'rail_q_m':q,'rail_v_mps':v,
                                    'ball_position_w':ball_position.tolist()}
            if floor in [a,b]:
                other_floor = b if a==floor else a
                if other_floor in shooter.geoms and other_floor not in shooter.foot_geoms:
                    nonfoot_floor = True
            if (a in shooter.geoms and b in keeper.geoms) or (b in shooter.geoms and a in keeper.geoms):
                robot_collision = True
        if step % 10 == 0:
            # Preserve FreeKick's phase-2 sensor contract (world pose from xpos).
            kick.update(data,data.xpos[ball].copy(),data.qvel[reader.ball_v:reader.ball_v+3].copy(),step*model.opt.timestep)
            shooter_tilt = tilt(data.xquat[shooter.torso])
            max_torso,max_keeper_torso = max(max_torso,shooter_tilt),max(max_keeper_torso,tilt(data.xquat[keeper.torso]))
            if first_fall is None and (nonfoot_floor or data.qpos[kick.root_q+2]<0.15 or data.xpos[shooter.torso,2]<0.45 or shooter_tilt>70):
                first_fall = now
        max_base_error = max(max_base_error,1-abs(float(np.dot(base_quat,data.xquat[keeper.pelvis]))))
        max_base_height_error = max(max_base_height_error,abs(float(data.xpos[keeper.pelvis,2])-base_z))
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise FloatingPointError('Nonfinite simulation state')
        previous_ball,previous_q,previous_v = ball_position.copy(),q,v
    loop_s = time.perf_counter()-loop_start
    final_q = float(data.qpos[rail.qpos])
    goal = bool(goal_crossing and goal_crossing['inside'])
    if goal:
        outcome = 'goal'
    elif first_keeper and first_foot and approach_crossing:
        outcome = 'save_observed'
    elif goal_crossing and not goal_crossing['inside']:
        outcome = 'miss'
    else:
        outcome = 'unresolved_no_goal'
    changed = [p for p,h in {**external,**old_sources}.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    errors = []
    def require(ok,message):
        if not ok: errors.append(message)
    require(first_foot is not None,'No physical FreeKick foot contact')
    require(first_fall is None and not robot_collision,'Instability or robot-robot collision')
    require(qmin>=-limits.joint_travel-0.002 and qmax<=limits.joint_travel+0.002,'Slider travel violation')
    require(max_v<=limits.measured_speed_acceptance and max_a<=limits.measured_acceleration_acceptance,'Motion acceptance violation')
    require(max_ref_v<=limits.reference_speed+1e-8 and max_ref_a<=limits.reference_acceleration+1e-8,'Reference bounds violated')
    require(max_keeper_torso<25 and max_base_error<1e-8 and max_base_height_error<1e-8,'Keeper mechanism unstable')
    require(not changed and not any(w.number for w in data.warning),'Changed files or engine warning')
    if agent:
        require(agent.detection_time is not None,'Agent did not detect shot')
        require(agent.episode_end_time is not None and abs(final_q)<0.015,'Agent did not finish and return to center')
    prediction_at_detection = agent.first_prediction if agent else None
    prediction_error = None
    arrival_error = None
    if prediction_at_detection and approach_crossing:
        prediction_error = abs(prediction_at_detection['y_w']-approach_crossing['position_w'][1])
        arrival_error = agent.detection_time+prediction_at_detection['eta_s']-approach_crossing['time_sim_s']
    result = {'scenario':args.scenario,'configuration':scenario,'initial_state_sha256':initial_hash,'initial_state':initial_state,'mode':args.mode,'simulated_s':float(data.time),
              'timing':{'scene_build_s':build_s,'policy_load_s':load_s,'loop_wall_s':loop_s,'script_wall_s':time.perf_counter()-START},
              'observation_contract':{'rate_hz':50,'world_x':'toward_goal','world_z':'up','rail_positive':'keeper_left_world_minus_y',
                                      'approach_plane_x':reader.plane_x,'goal_plane_x':5.0,
                                      'ball_position_source':'current_integrated_ball_freejoint_qpos',
                                      'ball_velocity_source':'current_ball_freejoint_linear_qvel'},
              'agent':{'detection_time_sim_s':agent.detection_time if agent else None,
                       'first_command_time_sim_s':agent.first_command_time if agent else None,
                       'first_physical_motion_time_sim_s':first_movement,
                       'first_forward_ball_observed_sim_s':first_forward_observed,
                       'detection_latency_from_measured_foot_contact_s':agent.detection_time-first_foot['time_sim_s'] if agent and agent.detection_time and first_foot else None,
                       'command_reaction_after_detection_s':agent.first_command_time-agent.detection_time if agent and agent.first_command_time else None,
                       'physical_reaction_after_detection_s':first_movement-agent.detection_time if agent and first_movement else None,
                       'first_prediction_estimated':prediction_at_detection,
                       'episode_end_observed_time_s':agent.episode_end_time if agent else None,
                       'final_state':agent.state if agent else 'FIXED',
                       'decision_events':decision_events},
              'evaluation':{'first_foot_ball':first_foot,'foot_peak_force_n':foot_peak_force,'velocity_after_first_foot_contact_w':first_foot_velocity,'peak_ball_speed_mps':peak_ball_speed,'first_keeper_ball':first_keeper,
                            'keeper_peak_contact_force_n':contact_peak,'approach_crossing_measured':approach_crossing,
                            'prediction_lateral_error_vs_measured_crossing_m':prediction_error,
                            'predicted_minus_actual_arrival_time_s':arrival_error,
                            'goal_crossing_measured':goal_crossing,'goal_detected':goal,'provisional_outcome_not_save_classification':outcome,
                            'shooter_fall_time_s':first_fall,'shooter_max_tilt_deg':max_torso,
                            'keeper_max_tilt_deg':max_keeper_torso,'robot_robot_contact':robot_collision,
                            'ball_net_displacement_m':float(np.linalg.norm(previous_ball-ball0))},
              'rail':{'qmin_m':qmin,'qmax_m':qmax,'final_q_m':final_q,'peak_speed_mps':max_v,
                      'peak_acceleration_mps2':max_a,'peak_force_n':max_force,'reference_peak_speed_mps':max_ref_v,
                      'reference_peak_acceleration_mps2':max_ref_a,'max_base_orientation_error':max_base_error,
                      'max_base_height_error_m':max_base_height_error},
              'initial_low_ball_collision_aabb_envelope':coverage,
              'mapping':{'actuators':model.nu,'shooter_motor_ids':shooter.actuators.tolist(),
                         'keeper_motor_ids':keeper.actuators.tolist(),'rail_motor_id':rail.actuator},
              'original_files_checked':len(external),'previous_phase_sources_checked':len(old_sources),
              'files_changed':changed,'engine_warnings':[int(w.number) for w in data.warning],
              'failures':errors,'passed':not errors,'trace':trace}
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['scenario','mode','timing','evaluation','passed','failures']}))
    return 0 if not errors else 2


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['probe','fixed','agent','capacity_left','capacity_right'],default='agent')
    p.add_argument('--scenario',choices=list(SCENARIOS),default='center')
    p.add_argument('--duration',type=float,default=14)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    try:
        sys.exit(run(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
