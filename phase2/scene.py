"""Own runtime composition. External XML/meshes are read in place, never exported."""
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np


@dataclass
class RobotIndex:
    actuators: np.ndarray
    joints: np.ndarray
    qpos: np.ndarray
    dofs: np.ndarray
    bodies: set
    geoms: set
    foot_geoms: set
    pelvis: int
    torso: int

    @classmethod
    def resolve(cls, model, prefix):
        pelvis = model.body(prefix + "pelvis").id
        bodies = {pelvis}
        for body in range(1, model.nbody):
            if int(model.body_parentid[body]) in bodies:
                bodies.add(body)
        actuators = np.array([
            i for i in range(model.nu)
            if int(model.jnt_bodyid[int(model.actuator_trnid[i, 0])]) in bodies
        ], dtype=int)
        joints = model.actuator_trnid[actuators, 0].astype(int)
        if len(joints) != 29 or len(set(joints.tolist())) != 29:
            raise ValueError(f"Expected 29 independent motors for {prefix!r}")
        if not np.all(model.jnt_type[joints] == mujoco.mjtJoint.mjJNT_HINGE):
            raise ValueError("Motor mapping includes a non-hinge joint")
        geoms = {i for i in range(model.ngeom) if int(model.geom_bodyid[i]) in bodies}
        feet = {i for i in geoms if "ankle_roll_link" in model.body(int(model.geom_bodyid[i])).name}
        return cls(actuators, joints, model.jnt_qposadr[joints].copy(),
                   model.jnt_dofadr[joints].copy(), bodies, geoms, feet,
                   pelvis, model.body(prefix + "torso_link").id)

    def describe(self, model):
        return {
            "actuator_ids": self.actuators.tolist(),
            "joint_names": [model.joint(int(i)).name for i in self.joints],
            "qpos_addresses": self.qpos.tolist(),
            "dof_addresses": self.dofs.tolist(),
            "body_count": len(self.bodies), "geom_count": len(self.geoms),
            "pelvis_body_id": self.pelvis,
        }


def build_scene(deploy_root: Path, unitree_root: Path, keeper_y):
    spec = mujoco.MjSpec.from_file(str(deploy_root / "g1_description/scene_with_ball.xml"))
    if keeper_y is not None:
        keeper = mujoco.MjSpec.from_file(str(unitree_root / "unitree_robots/g1/g1_29dof.xml"))
        # Runtime-only physical simplification: no floating base for goalkeeper.
        for joint in list(keeper.joints):
            if joint.type == mujoco.mjtJoint.mjJNT_FREE:
                keeper.delete(joint)
        for key in list(keeper.keys):
            keeper.delete(key)
        for number, geom in enumerate(keeper.geoms):
            if not geom.name:
                geom.name = f"geom_{number:03d}"
        origin = spec.worldbody.add_frame(
            name="goalkeeper_origin", pos=[4.2, keeper_y, 0.0], quat=[0, 0, 0, 1])
        spec.attach(keeper, prefix="gk/", frame=origin)
    # Deliberately do not call to_xml/to_file/to_zip: no derived asset is saved.
    model = spec.compile()
    model.opt.timestep = 0.002
    data = mujoco.MjData(model)
    shooter = RobotIndex.resolve(model, "")
    goalkeeper = RobotIndex.resolve(model, "gk/") if keeper_y is not None else None
    if goalkeeper:
        for field in ["actuators", "qpos", "dofs"]:
            if set(getattr(shooter, field)) & set(getattr(goalkeeper, field)):
                raise ValueError(f"Overlapping robot {field}")
    mujoco.mj_forward(model, data)
    return model, data, shooter, goalkeeper
