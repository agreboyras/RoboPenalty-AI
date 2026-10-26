"""Adapter to the existing local runtime; no third-party policy is vendored."""
import contextlib
import io
import sys

import numpy as np


class FreeKickAdapter:
    def __init__(self, deploy_root, model, index):
        sys.path.insert(0, str(deploy_root))
        # Import existing implementations without executing the Hydra entrypoint.
        from common.ctrlcomp import StateAndCmd, PolicyOutput
        from common.utils import FSMCommand, FSMStateName, get_gravity_orientation
        from deploy_mujoco.deploy_mujoco import _FreeKickOnlyFSM, quat_to_matrix
        self.commands, self.names = FSMCommand, FSMStateName
        self.gravity, self.rotation = get_gravity_orientation, quat_to_matrix
        self.index = index
        self.root_q = int(model.jnt_qposadr[model.joint("floating_base_joint").id])
        self.root_v = int(model.jnt_dofadr[model.joint("floating_base_joint").id])
        self.state, self.output = StateAndCmd(29), PolicyOutput(29)
        self.state.target_y_bias = 0.0
        self.initialization_output = io.StringIO()
        with contextlib.redirect_stdout(self.initialization_output):
            self.fsm = _FreeKickOnlyFSM(self.state, self.output)
        self.target = np.zeros(29, dtype=np.float32)
        self.kp = np.zeros(29, dtype=np.float32)
        self.kd = np.zeros(29, dtype=np.float32)
        self.fixed_requested = self.kick_requested = False
        self.sensor_updates = 0
        self.first_policy_time = None

    def command_before_step(self, sim_time):
        current = self.fsm.cur_policy.name
        if not self.fixed_requested and current == self.names.PASSIVE:
            self.state.skill_cmd = self.commands.POS_RESET
            self.fixed_requested = True
        elif (self.fixed_requested and not self.kick_requested
              and current == self.names.FIXEDPOSE and sim_time >= 0.4):
            self.state.skill_cmd = self.commands.CMD_FREEKICK
            self.kick_requested = True

    def torque(self, data, limits):
        i = self.index
        return np.clip(self.kp * (self.target - data.qpos[i.qpos])
                       - self.kd * data.qvel[i.dofs], -limits, limits)

    def update(self, data, ball_pos, ball_vel, sim_time):
        i, s = self.index, self.state
        quat = data.qpos[self.root_q + 3:self.root_q + 7]
        omega = data.qvel[self.root_v + 3:self.root_v + 6]
        s.q, s.dq = data.qpos[i.qpos].copy(), data.qvel[i.dofs].copy()
        s.gravity_ori = self.gravity(quat)
        s.ang_vel = omega.copy()
        s.root_lin_vel_b = (self.rotation(quat).T @ data.qvel[self.root_v:self.root_v + 3]).astype(np.float32)
        s.root_ang_vel_b = omega.astype(np.float32)
        s.torso_pos_w = data.xpos[i.torso].astype(np.float32)
        s.torso_quat_w = data.xquat[i.torso].astype(np.float32)
        s.pelvis_pos_w = data.qpos[self.root_q:self.root_q + 3].astype(np.float32)
        s.pelvis_quat_w = quat.astype(np.float32)
        if self.sensor_updates % 5 == 0:
            s.ball_pos_w = ball_pos.astype(np.float32)
            s.ball_vel_w = ball_vel.astype(np.float32)
        self.sensor_updates += 1
        with contextlib.redirect_stdout(self.initialization_output):
            self.fsm.run()
        if self.first_policy_time is None and self.fsm.cur_policy.name == self.names.SKILL_FREEKICK:
            self.first_policy_time = sim_time
        self.target = self.output.actions.copy()
        self.kp, self.kd = self.output.kps.copy(), self.output.kds.copy()
