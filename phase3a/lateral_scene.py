"""Runtime-only G1 composition with a physical one-axis goalkeeper carriage."""
from dataclasses import dataclass
from pathlib import Path
import sys

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'phase2'))
from scene import RobotIndex


@dataclass(frozen=True)
class Limits:
    joint_travel: float = 0.75
    command_travel: float = 0.65
    reference_speed: float = 0.30
    reference_acceleration: float = 0.50
    drive_acceleration: float = 1.0
    force: float = 120.0
    velocity_guard: float = 0.35
    # Physical contact impulses are not bounded by the reference generator.
    measured_speed_acceptance: float = 0.40
    measured_acceleration_acceptance: float = 8.0


@dataclass
class RailIndex:
    joint: int
    qpos: int
    dof: int
    actuator: int
    carriage: int
    carried_mass: float
    damping: float


def build_scene(deploy, unitree, limits):
    spec = mujoco.MjSpec.from_file(str(deploy / 'g1_description/scene_with_ball.xml'))
    keeper = mujoco.MjSpec.from_file(str(unitree / 'unitree_robots/g1/g1_29dof.xml'))
    for joint in list(keeper.joints):
        if joint.type == mujoco.mjtJoint.mjJNT_FREE:
            keeper.delete(joint)
    for key in list(keeper.keys):
        keeper.delete(key)
    for number, geom in enumerate(keeper.geoms):
        if not geom.name:
            geom.name = f'geom_{number:03d}'
    # This owned support has no contact geometry. It carries the entire G1 mass.
    carriage = spec.worldbody.add_body(name='keeper_carriage', pos=[4.2, 0, 0])
    carriage.mass = 0.2
    carriage.inertia = [0.001, 0.001, 0.001]
    carriage.explicitinertial = True
    carriage.add_joint(name='keeper_slide', type=mujoco.mjtJoint.mjJNT_SLIDE,
                       axis=[0, -1, 0], limited=True,
                       range=[-limits.joint_travel, limits.joint_travel],
                       damping=70.0, armature=0.2,
                       solref_limit=[0.004, 1], solimp_limit=[0.99, 0.999, 0.001, 0.5, 2])
    frame = carriage.add_frame(name='keeper_facing', quat=[0, 0, 0, 1])
    spec.attach(keeper, prefix='gk/', frame=frame)
    spec.add_actuator(name='keeper_slide_motor', target='keeper_slide',
                      trntype=mujoco.mjtTrn.mjTRN_JOINT,
                      gear=[1, 0, 0, 0, 0, 0], ctrllimited=True,
                      ctrlrange=[-limits.force, limits.force], forcelimited=True,
                      forcerange=[-limits.force, limits.force])
    model = spec.compile()
    model.opt.timestep = 0.002
    data = mujoco.MjData(model)
    shooter, goalkeeper = RobotIndex.resolve(model, ''), RobotIndex.resolve(model, 'gk/')
    joint, body = model.joint('keeper_slide').id, model.body('keeper_carriage').id
    rail = RailIndex(joint, int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint]),
                     model.actuator('keeper_slide_motor').id, body,
                     float(model.body_subtreemass[body]), float(model.dof_damping[model.jnt_dofadr[joint]]))
    for field in ['actuators', 'qpos', 'dofs']:
        a, b = set(getattr(shooter, field)), set(getattr(goalkeeper, field))
        rail_id = {'actuators': rail.actuator, 'qpos': rail.qpos, 'dofs': rail.dof}[field]
        if a & b or rail_id in a or rail_id in b:
            raise AssertionError(f'Overlapping {field}')
    if model.nu != 59:
        raise AssertionError('Expected 29 shooter + 29 keeper + 1 slider actuators')
    mujoco.mj_forward(model, data)
    return model, data, shooter, goalkeeper, rail
