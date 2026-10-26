"""Two-G1 feasibility experiment, not an autonomous goalkeeper implementation."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import traceback
import zlib

STARTED = time.perf_counter()
sys.dont_write_bytecode = True
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import mujoco
import numpy as np
import yaml

from scene import build_scene
from freekick_adapter import FreeKickAdapter


def tilt(quat):
    w, x, y, z = quat
    return math.degrees(math.acos(float(np.clip(1 - 2 * (x*x + y*y), -1, 1))))


def contact_event(model, data, contact, sim_time):
    force = np.zeros(6)
    mujoco.mj_contactForce(model, data, contact, force)
    c = data.contact[contact]
    return {"time_sim_s": sim_time,
            "geoms": [model.geom(int(c.geom1)).name, model.geom(int(c.geom2)).name],
            "bodies": [model.body(int(model.geom_bodyid[g])).name for g in [c.geom1, c.geom2]],
            "normal_force_n": float(force[0])}


def png(path, pixels):
    height, width, _ = pixels.shape
    def chunk(name, payload):
        return struct.pack('!I', len(payload)) + name + payload + struct.pack('!I', zlib.crc32(name + payload) & 0xffffffff)
    raw = b''.join(b'\0' + pixels[row].tobytes() for row in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def run(args):
    root = Path(__file__).resolve().parents[2]
    deploy, unitree = root / 'RoboNaldo_Deploy', root / 'unitree_mujoco'
    output = Path(args.output).resolve()
    if not output.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Results must stay inside RoboPenalty')
    output.parent.mkdir(parents=True, exist_ok=True)
    source_paths = [p for directory in ['g1_description', 'policy', 'common', 'FSM', 'deploy_mujoco', 'tools']
                    for p in (deploy / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    source_paths += [p for p in (unitree / 'unitree_robots/g1').rglob('*') if p.is_file()]
    source_paths += [unitree / 'LICENSE']
    hashes_before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    keeper_y = None if args.case == 'single' else (2.5 if args.case == 'clear' else args.keeper_y)
    init_start = time.perf_counter()
    model, data, shooter, keeper = build_scene(deploy, unitree, keeper_y)
    build_s = time.perf_counter() - init_start
    with (deploy / 'deploy_mujoco/config/mujoco_freekick.yaml').open() as f:
        config = yaml.safe_load(f)
    limits = np.asarray(config['tau_limit'])
    policy_start = time.perf_counter()
    adapter = FreeKickAdapter(deploy, model, shooter)
    policy_load_s = time.perf_counter() - policy_start
    ball_id, ball_geom = model.body('ball').id, model.geom('ball_geom').id
    ball_joint = int(model.body_jntadr[ball_id])
    ball_v = int(model.jnt_dofadr[ball_joint])
    floor = model.geom('floor').id
    keeper_target = np.zeros(29)
    if keeper:
        # Own diagnostic stance, not a copied pose or learned goalkeeper skill.
        for k, j in enumerate(keeper.joints):
            name = model.joint(int(j)).name
            if 'shoulder_roll' in name:
                keeper_target[k] = 0.25 if 'left_' in name else -0.25
            elif 'elbow' in name:
                keeper_target[k] = 0.30
        data.qpos[keeper.qpos] = keeper_target
        mujoco.mj_forward(model, data)
    initial_ball = data.xpos[ball_id].copy()
    initial_keeper = data.xpos[keeper.pelvis].copy() if keeper else None
    previous_ball = initial_ball.copy()
    first_foot = first_keeper = first_fall = goal = None
    first_nonfoot_floor = None
    keeper_contacts, max_keeper_force = 0, 0.0
    min_pelvis, min_torso, max_tilt = math.inf, math.inf, 0.0
    keeper_max_joint_error, keeper_max_drift, max_ball_speed = 0.0, 0.0, 0.0
    max_ball_x = float(initial_ball[0])
    max_contacts, unintended_contact = 0, False
    peak_keeper_torque, max_shooter_robot_contacts = 0.0, 0
    before_keeper_velocity = after_keeper_velocity = None
    keeper_event_time = None
    renderer = None
    snapshot_error = None
    snapshot_path = None
    if args.snapshot:
        try:
            model.vis.global_.offwidth = 1280
            model.vis.global_.offheight = 720
            renderer = mujoco.Renderer(model, height=720, width=1280)
        except Exception as exc:
            snapshot_error = repr(exc)
    def ball_state():
        return data.xpos[ball_id].copy(), data.qvel[ball_v:ball_v+3].copy()
    previous_velocity = data.qvel[ball_v:ball_v+3].copy()
    checkpoints = []
    checkpoint_times = [2.0, 4.0, 4.4, 6.0, args.duration]
    sim_start = time.perf_counter()
    real_first_foot = None
    steps = round(args.duration / model.opt.timestep)
    for step in range(steps):
        sim_time = step * model.opt.timestep  # Same event labeling convention as phase 1A.
        adapter.command_before_step(sim_time)
        data.ctrl[shooter.actuators] = adapter.torque(data, limits)
        if keeper:
            keeper_torque = np.clip(70 * (keeper_target - data.qpos[keeper.qpos])
                                    - 5 * data.qvel[keeper.dofs], -limits, limits)
            data.ctrl[keeper.actuators] = keeper_torque
            peak_keeper_torque = max(peak_keeper_torque, float(np.max(np.abs(keeper_torque))))
        mujoco.mj_step(model, data)
        ball_pos, ball_vel = ball_state()
        max_contacts = max(max_contacts, data.ncon)
        max_ball_speed = max(max_ball_speed, float(np.linalg.norm(ball_vel)))
        max_ball_x = max(max_ball_x, float(ball_pos[0]))
        for n in range(data.ncon):
            c = data.contact[n]
            a, b = int(c.geom1), int(c.geom2)
            other = b if a == ball_geom else a if b == ball_geom else None
            if other in shooter.foot_geoms and first_foot is None:
                first_foot = contact_event(model, data, n, sim_time)
                real_first_foot = time.perf_counter() - STARTED
            if keeper and other in keeper.geoms:
                event = contact_event(model, data, n, sim_time)
                keeper_contacts += 1
                max_keeper_force = max(max_keeper_force, event['normal_force_n'])
                if first_keeper is None:
                    first_keeper = event
                    first_keeper['ball_position_w'] = ball_pos.tolist()
                    before_keeper_velocity = previous_velocity.tolist()
                    keeper_event_time = sim_time
            if floor in [a, b]:
                nonfloor = b if a == floor else a
                if nonfloor in shooter.geoms and nonfloor not in shooter.foot_geoms:
                    first_nonfoot_floor = first_nonfoot_floor or sim_time or 1e-12
            if keeper and ((a in shooter.geoms and b in keeper.geoms) or
                           (b in shooter.geoms and a in keeper.geoms)):
                unintended_contact = True
                max_shooter_robot_contacts += 1
        if keeper_event_time is not None and after_keeper_velocity is None and sim_time >= keeper_event_time + 0.05:
            after_keeper_velocity = ball_vel.tolist()
        if goal is None and previous_ball[0] < 5.0 <= ball_pos[0]:
            alpha = (5.0 - previous_ball[0]) / (ball_pos[0] - previous_ball[0])
            cross = previous_ball + alpha * (ball_pos - previous_ball)
            goal = {'time_sim_s': sim_time, 'cross_position_w': cross.tolist(),
                    'inside': bool(abs(cross[1]) <= 1.5 and 0 <= cross[2] <= 1.8)}
        if step % 10 == 0:
            adapter.update(data, ball_pos, ball_vel, sim_time)
            pelvis_z = float(data.qpos[adapter.root_q + 2])
            torso_z = float(data.xpos[shooter.torso, 2])
            torso_tilt = tilt(data.xquat[shooter.torso])
            min_pelvis, min_torso = min(min_pelvis, pelvis_z), min(min_torso, torso_z)
            max_tilt = max(max_tilt, torso_tilt)
            if first_fall is None and (first_nonfoot_floor is not None or pelvis_z < 0.15 or torso_z < 0.45 or torso_tilt > 70):
                first_fall = {'time_sim_s': sim_time, 'pelvis_z': pelvis_z, 'torso_z': torso_z,
                              'torso_tilt_deg': torso_tilt, 'nonfoot_floor': first_nonfoot_floor is not None}
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise FloatingPointError('Non-finite robot state')
        if keeper:
            keeper_max_joint_error = max(keeper_max_joint_error, float(np.max(np.abs(data.qpos[keeper.qpos] - keeper_target))))
            keeper_max_drift = max(keeper_max_drift, float(np.linalg.norm(data.xpos[keeper.pelvis] - initial_keeper)))
        if len(checkpoints) < len(checkpoint_times) and data.time + 1e-9 >= checkpoint_times[len(checkpoints)]:
            checkpoints.append({'time_sim_s': float(data.time),
                                'shooter_joint_qpos': data.qpos[shooter.qpos].tolist(),
                                'shooter_root_qpos': data.qpos[adapter.root_q:adapter.root_q+7].tolist()})
        if renderer is not None and snapshot_path is None and sim_time >= 4.3:
            try:
                camera = mujoco.MjvCamera()
                camera.lookat[:] = [2.6, 0.5 if args.case == 'clear' else 0, 0.8]
                camera.distance, camera.azimuth, camera.elevation = 8.0, -100, -18
                renderer.update_scene(data, camera=camera)
                pixels = renderer.render()
                snapshot_path = str(output.with_suffix('.png'))
                png(Path(snapshot_path), pixels)
            except Exception as exc:
                snapshot_error = repr(exc)
                renderer.close()
                renderer = None
        previous_ball, previous_velocity = ball_pos.copy(), ball_vel.copy()
    sim_wall_s = time.perf_counter() - sim_start
    if renderer is not None:
        renderer.close()
    final_ball, final_velocity = ball_state()
    changed = [p for p, digest in hashes_before.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest]
    if changed:
        raise RuntimeError(f'Original source changed: {changed}')
    warnings = [{'type': str(mujoco.mjtWarning(i)), 'count': int(w.number), 'lastinfo': int(w.lastinfo)}
                for i, w in enumerate(data.warning) if w.number]
    result = {
        'case': args.case, 'keeper_y': keeper_y, 'simulated_s': float(data.time), 'steps': steps,
        'timing': {'scene_build_s': build_s, 'policy_initialization_s': policy_load_s,
                   'simulation_loop_wall_s': sim_wall_s, 'internal_total_s': time.perf_counter() - STARTED,
                   'simulation_loop_includes_snapshot': args.snapshot,
                   'first_foot_contact_wall_from_script_s': real_first_foot},
        'model': {'nq': model.nq, 'nv': model.nv, 'nu': model.nu, 'nbody': model.nbody,
                  'shooter': shooter.describe(model), 'keeper': keeper.describe(model) if keeper else None},
        'physics': {'first_shooter_foot_ball': first_foot, 'first_keeper_ball': first_keeper,
                    'keeper_contact_samples': keeper_contacts, 'max_keeper_contact_force_n': max_keeper_force,
                    'ball_velocity_before_keeper_w': before_keeper_velocity,
                    'ball_velocity_50ms_after_keeper_w': after_keeper_velocity,
                    'initial_ball_position_w': initial_ball.tolist(), 'final_ball_position_w': final_ball.tolist(),
                    'final_ball_velocity_w': final_velocity.tolist(),
                    'ball_net_displacement_m': float(np.linalg.norm(final_ball - initial_ball)),
                    'max_ball_speed_mps': max_ball_speed, 'max_ball_x': max_ball_x,
                    'goal_crossing': goal, 'goal_detected': bool(goal and goal['inside']),
                    'shooter_first_fall': first_fall, 'shooter_min_pelvis_z': min_pelvis,
                    'shooter_min_torso_z': min_torso, 'shooter_max_tilt_deg': max_tilt,
                    'keeper_base_max_drift_m': keeper_max_drift,
                    'keeper_max_joint_error_rad': keeper_max_joint_error,
                    'keeper_peak_motor_torque_nm': peak_keeper_torque,
                    'shooter_keeper_contact': unintended_contact, 'max_contact_count': max_contacts},
        'control': {'first_freekick_sim_s': adapter.first_policy_time,
                    'robot_actuator_sets_disjoint': keeper is None or not bool(set(shooter.actuators) & set(keeper.actuators)),
                    'policy_observation_dim': 547, 'policy_action_dim': 29},
        'simplifications': ['Goalkeeper pelvis physically anchored; 29 joints remain dynamic under posture PD.',
                            'Goalkeeper uses official Unitree mesh collisions; shooter uses existing RoboNaldo model.',
                            'Original visual goal has contacts disabled; original backstop box retained.',
                            'No learned or autonomous goalkeeper. No visual ghost robot.'],
        'external_inputs': {'deploy_root': str(deploy), 'goalkeeper_model': str(unitree / 'unitree_robots/g1/g1_29dof.xml'),
                            'goalkeeper_license': str(unitree / 'LICENSE'), 'files_sha256': hashes_before,
                            'original_files_changed': changed},
        'warnings': warnings, 'snapshot': snapshot_path, 'snapshot_error': snapshot_error,
        'shooter_checkpoints': checkpoints,
        'sampling': {'ball_speed_hz': 500, 'shooter_stability_hz': 50},
    }
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['case', 'timing', 'physics', 'warnings', 'snapshot', 'snapshot_error']}, indent=2))
    # These diagnostics are meaningful criteria, rather than a test of mere completion.
    if first_foot is None or np.linalg.norm(final_ball - initial_ball) < 0.5 or first_fall is not None:
        return 2
    if args.case == 'block' and (first_keeper is None or max_keeper_force <= 0):
        return 3
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['single', 'clear', 'block'], required=True)
    parser.add_argument('--duration', type=float, default=14.0)
    parser.add_argument('--keeper-y', type=float, default=0.0)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
