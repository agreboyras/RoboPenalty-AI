"""Physical slider tests, optional native MuJoCo viewer, bounded scripted motion."""
import argparse
import contextlib
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import traceback

START = time.perf_counter()
sys.dont_write_bytecode = True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import mujoco
import numpy as np
import yaml

from lateral_scene import build_scene, Limits
from lateral_control import LateralControl, schedule
from freekick_adapter import FreeKickAdapter


def angle(quat):
    return math.degrees(math.acos(float(np.clip(1 - 2 * (quat[1]**2 + quat[2]**2), -1, 1))))


def run(args):
    folder = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    if not output.is_relative_to(folder) or output.exists():
        raise ValueError('Output must be new and inside RoboPenalty')
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = folder.parent
    deploy, unitree = workspace / 'RoboNaldo_Deploy', workspace / 'unitree_mujoco'
    phase2 = folder / 'phase2'
    # The phase-2 manifest includes 209 original controller/config/asset files.
    original_manifest = json.loads((phase2 / 'results/benchmark/single_01.json').read_text(encoding='utf-8'))['external_inputs']['files_sha256']
    phase2_sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in phase2.glob('*.py')}
    before = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original_manifest}
    if before != original_manifest:
        raise AssertionError('Original dependencies differ from phase 2')
    limits = Limits()
    t = time.perf_counter()
    model, data, shooter, keeper, rail = build_scene(deploy, unitree, limits)
    build_s = time.perf_counter() - t
    with (deploy / 'deploy_mujoco/config/mujoco_freekick.yaml').open() as f:
        torques = np.asarray(yaml.safe_load(f)['tau_limit'])
    t = time.perf_counter()
    kick = FreeKickAdapter(deploy, model, shooter)
    load_s = time.perf_counter() - t
    posture = np.zeros(29)
    for n, j in enumerate(keeper.joints):
        name = model.joint(int(j)).name
        if 'shoulder_roll' in name:
            posture[n] = 0.25 if 'left_' in name else -0.25
        elif 'elbow' in name:
            posture[n] = 0.30
    # Initialization only: no qpos/qvel assignment occurs inside the simulation loop.
    data.qpos[keeper.qpos] = posture
    mujoco.mj_forward(model, data)
    control = LateralControl(limits, rail)
    commands = schedule(args.case)
    command_index = 0
    events = []
    trace = []
    pending = []
    key_lock = threading.Lock()
    def keyboard(key):
        selected = {263: 0.60, 262: -0.60, ord('L'): 0.60,
                    ord('R'): -0.60, ord('C'): 0.0, 32: 0.0}.get(key)
        if selected is not None:
            with key_lock:
                pending.append(selected)
    viewer = None
    viewer_open_s = 0.0
    sync_s = sleep_s = 0.0
    sync_count = 0
    if args.viewer:
        import mujoco.viewer as mjviewer
        t = time.perf_counter()
        viewer = mjviewer.launch_passive(model, data, key_callback=keyboard)
        viewer_open_s = time.perf_counter() - t
        with viewer.lock():
            viewer.cam.lookat[:] = [2.6, 0, 0.8]
            viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 8, -100, -18
        print('Controls: L/left arrow = goalkeeper left (world -Y); R/right arrow = right; C/space = center.', flush=True)
    ball, ball_geom, floor = model.body('ball').id, model.geom('ball_geom').id, model.geom('floor').id
    bv = int(model.jnt_dofadr[int(model.body_jntadr[ball])])
    ball0 = data.xpos[ball].copy()
    prev_ball = ball0.copy()
    first_foot = first_keeper = first_fall = goal = None
    nonfoot_floor = robot_contact = False
    force_peak = max_speed = max_accel = max_ref_speed = max_ref_accel = max_error = 0.0
    keeper_contact_force = 0.0
    qmin = qmax = 0.0
    max_orientation_error = max_height_error = max_keeper_tilt = max_shooter_tilt = 0.0
    min_pelvis = float('inf')
    body0 = data.xpos[keeper.pelvis].copy()
    keeper_quat0 = data.xquat[keeper.pelvis].copy()
    first_real_foot = None
    checkpoints = []
    previous_v = float(data.qvel[rail.dof])
    completed = 0
    sync_interval = 1 / 30
    next_sync = 0.0
    loop_start = time.perf_counter()
    try:
        for step in range(round(args.duration / model.opt.timestep)):
            sim_t = step * model.opt.timestep
            while command_index < len(commands) and sim_t + 1e-10 >= commands[command_index][0]:
                raw = commands[command_index][1]
                control.select(raw)
                events.append({'time_sim_s': sim_t, 'raw_target_m': raw, 'accepted_target_m': control.goal, 'source': 'script'})
                command_index += 1
            with key_lock:
                user_commands = pending[:]
                pending.clear()
            for raw in user_commands:
                control.select(raw)
                events.append({'time_sim_s': sim_t, 'raw_target_m': raw, 'accepted_target_m': control.goal, 'source': 'keyboard'})
            control.advance_reference(model.opt.timestep)
            kick.command_before_step(sim_t)
            with viewer.lock() if viewer else contextlib.nullcontext():
                data.ctrl[shooter.actuators] = kick.torque(data, torques)
                data.ctrl[keeper.actuators] = np.clip(70 * (posture - data.qpos[keeper.qpos]) - 5 * data.qvel[keeper.dofs], -torques, torques)
                data.ctrl[rail.actuator] = control.force(float(data.qpos[rail.qpos]), float(data.qvel[rail.dof]))
                force_peak = max(force_peak, abs(float(data.ctrl[rail.actuator])))
                mujoco.mj_step(model, data)
                q, v = float(data.qpos[rail.qpos]), float(data.qvel[rail.dof])
                acceleration_fd = (v - previous_v) / model.opt.timestep
                previous_v = v
                qmin, qmax = min(qmin, q), max(qmax, q)
                max_speed, max_accel = max(max_speed, abs(v)), max(max_accel, abs(acceleration_fd))
                max_ref_speed = max(max_ref_speed, abs(control.velocity))
                max_ref_accel = max(max_ref_accel, abs(control.acceleration))
                max_error = max(max_error, abs(q - control.position))
                pos, vel = data.xpos[ball].copy(), data.qvel[bv:bv+3].copy()
                for n in range(data.ncon):
                    c = data.contact[n]
                    a, b = int(c.geom1), int(c.geom2)
                    other = b if a == ball_geom else a if b == ball_geom else None
                    if other in shooter.foot_geoms and first_foot is None:
                        first_foot = {'time_sim_s': sim_t, 'geom': model.geom(other).name}
                        first_real_foot = time.perf_counter() - START
                    if other in keeper.geoms:
                        f = np.zeros(6)
                        mujoco.mj_contactForce(model, data, n, f)
                        keeper_contact_force = max(keeper_contact_force, float(f[0]))
                        if first_keeper is None:
                            first_keeper = {'time_sim_s': sim_t, 'geom': model.geom(other).name,
                                            'rail_position_m': q, 'rail_speed_mps': v,
                                            'ball_position_w': pos.tolist(), 'normal_force_n': float(f[0])}
                    if floor in [a, b]:
                        g = b if a == floor else a
                        if g in shooter.geoms and g not in shooter.foot_geoms:
                            nonfoot_floor = True
                    if (a in shooter.geoms and b in keeper.geoms) or (b in shooter.geoms and a in keeper.geoms):
                        robot_contact = True
                if goal is None and prev_ball[0] < 5 <= pos[0]:
                    ratio = (5 - prev_ball[0]) / (pos[0] - prev_ball[0])
                    cross = prev_ball + ratio * (pos - prev_ball)
                    goal = {'time_sim_s': sim_t, 'inside': bool(abs(cross[1]) <= 1.5 and 0 <= cross[2] <= 1.8)}
                prev_ball = pos
                if step % 10 == 0:
                    kick.update(data, pos, vel, sim_t)
                    pelvis_z = float(data.qpos[kick.root_q+2])
                    torso_z = float(data.xpos[shooter.torso, 2])
                    shooter_tilt = angle(data.xquat[shooter.torso])
                    min_pelvis, max_shooter_tilt = min(min_pelvis, pelvis_z), max(max_shooter_tilt, shooter_tilt)
                    max_keeper_tilt = max(max_keeper_tilt, angle(data.xquat[keeper.torso]))
                    if first_fall is None and (nonfoot_floor or pelvis_z < 0.15 or torso_z < 0.45 or shooter_tilt > 70):
                        first_fall = sim_t
                max_orientation_error = max(max_orientation_error, 1 - abs(float(np.dot(keeper_quat0, data.xquat[keeper.pelvis]))))
                max_height_error = max(max_height_error, abs(float(data.xpos[keeper.pelvis, 2] - body0[2])))
                if step % 25 == 0:
                    trace.append({'time_sim_s': float(data.time), 'q_m': q, 'v_mps': v, 'acceleration_mps2': acceleration_fd,
                                  'reference_m': control.position, 'reference_v_mps': control.velocity,
                                  'reference_acceleration_mps2': control.acceleration, 'target_m': control.goal,
                                  'force_n': float(data.ctrl[rail.actuator])})
                if step in [999, 1999, 2199, 2999, 6999]:
                    checkpoints.append({'time_sim_s': float(data.time), 'shooter_joint_qpos': data.qpos[shooter.qpos].tolist(),
                                        'shooter_root_qpos': data.qpos[kick.root_q:kick.root_q+7].tolist()})
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                    raise FloatingPointError('Nonfinite simulation state')
            completed += 1
            if viewer and data.time + 1e-10 >= next_sync:
                if not viewer.is_running():
                    break
                t = time.perf_counter()
                viewer.sync()
                sync_s += time.perf_counter() - t
                sync_count += 1
                next_sync = data.time + sync_interval
                if not args.unpaced:
                    remaining = loop_start + data.time - time.perf_counter()
                    if remaining > 0:
                        t = time.perf_counter()
                        time.sleep(remaining)
                        sleep_s += time.perf_counter() - t
    finally:
        if viewer:
            viewer.close()
    loop_s = time.perf_counter() - loop_start
    changed = [p for p, h in {**before, **phase2_sources}.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
    warning_counts = [int(w.number) for w in data.warning]
    failures = []
    def require(condition, message):
        if not condition:
            failures.append(message)
    final_q, final_v = float(data.qpos[rail.qpos]), float(data.qvel[rail.dof])
    require(completed == round(args.duration / model.opt.timestep), 'Simulation ended early')
    require(first_foot is not None, 'No shooter foot contact')
    require(first_fall is None and not robot_contact, 'Shooter instability or robot-robot contact')
    require(not any(warning_counts) and not changed, 'Engine warning or changed reference file')
    require(qmin >= -limits.joint_travel - 0.002 and qmax <= limits.joint_travel + 0.002, 'Mechanical travel violation')
    require(max_ref_speed <= limits.reference_speed + 1e-8 and max_ref_accel <= limits.reference_acceleration + 1e-8, 'Reference velocity/acceleration violation')
    require(max_speed <= limits.measured_speed_acceptance and max_accel <= limits.measured_acceleration_acceptance, 'Measured motion exceeded acceptance envelope')
    require(max_orientation_error < 1e-8 and max_height_error < 1e-8, 'Rail did not preserve base orientation/height')
    require(max_keeper_tilt < 25, 'Keeper torso instability')
    if args.case == 'left':
        require(abs(final_q - 0.60) < 0.03, 'Left endpoint not reached')
    elif args.case == 'right':
        require(abs(final_q + 0.60) < 0.03, 'Right endpoint not reached')
    elif args.case == 'return':
        require(qmax > 0.55 and abs(final_q) < 0.03 and abs(final_v) < 0.03, 'Return to center failed')
    elif args.case == 'center':
        require(max(abs(qmin), abs(qmax)) < 0.03 and first_keeper is not None, 'Center hold/block failed')
    elif args.case == 'moving_contact':
        require(first_keeper is not None and abs(first_keeper['rail_speed_mps']) > 0.02 and keeper_contact_force > 0,
                'No physical ball contact while keeper was moving')
    elif args.case == 'limits':
        require(control.clamped_commands == 2 and qmax > 0.60 and qmin < -0.60, 'Out-of-range command test failed')
    result = {
        'case': args.case, 'viewer': args.viewer, 'paced': args.viewer and not args.unpaced,
        'simulated_s': float(data.time), 'steps': completed, 'limits': vars(limits),
        'timing': {'scene_build_s': build_s, 'policy_load_s': load_s, 'viewer_open_s': viewer_open_s,
                   'loop_wall_s': loop_s, 'viewer_sync_s': sync_s, 'viewer_sync_count': sync_count,
                   'pacing_sleep_s': sleep_s, 'script_elapsed_s': time.perf_counter()-START,
                   'first_foot_wall_from_script_s': first_real_foot},
        'rail': {'actuator': rail.actuator, 'qpos': rail.qpos, 'dof': rail.dof,
                 'mass_kg': rail.carried_mass, 'q_min_m': qmin, 'q_max_m': qmax,
                 'final_q_m': final_q, 'final_v_mps': final_v, 'peak_speed_mps': max_speed,
                 'peak_acceleration_mps2': max_accel, 'peak_force_n': force_peak,
                 'reference_peak_speed_mps': max_ref_speed, 'reference_peak_acceleration_mps2': max_ref_accel,
                 'max_tracking_error_m': max_error, 'clamped_commands': control.clamped_commands,
                 'max_base_quaternion_error': max_orientation_error, 'max_base_height_error_m': max_height_error},
        'physics': {'first_foot_ball': first_foot, 'first_keeper_ball': first_keeper,
                    'keeper_peak_contact_force_n': keeper_contact_force,
                    'ball_net_displacement_m': float(np.linalg.norm(data.xpos[ball]-ball0)),
                    'goal_detected': bool(goal and goal['inside']), 'shooter_first_fall_s': first_fall,
                    'shooter_min_pelvis_z': min_pelvis, 'shooter_max_tilt_deg': max_shooter_tilt,
                    'keeper_max_torso_tilt_deg': max_keeper_tilt, 'robot_robot_contact': robot_contact},
        'mapping': {'nu': model.nu, 'shooter': shooter.describe(model), 'keeper': keeper.describe(model)},
        'commands': events, 'trace': trace, 'shooter_checkpoints': checkpoints,
        'original_and_phase2_files_changed': changed, 'original_file_count': len(before),
        'engine_warning_counts': warning_counts, 'failures': failures, 'passed': not failures,
    }
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    with output.with_suffix('.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=trace[0].keys())
        writer.writeheader()
        writer.writerows(trace)
    print(json.dumps({k: result[k] for k in ['case','viewer','timing','rail','physics','passed','failures']}, indent=2))
    return 0 if not failures else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['center','left','right','return','moving_contact','limits','manual'], default='return')
    parser.add_argument('--duration', type=float, default=14)
    parser.add_argument('--viewer', action='store_true')
    parser.add_argument('--unpaced', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
