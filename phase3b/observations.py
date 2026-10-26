"""Causal observation boundary; the agent never receives a MuJoCo data object."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    time_s: float
    ball_position_w: tuple
    ball_velocity_w: tuple
    keeper_q: float
    keeper_v: float
    plane_x: float = 4.0
    rail_origin_y: float = 0.0
    rail_axis_y: float = -1.0


class ObservationReader:
    def __init__(self, model, rail):
        ball = model.body('ball').id
        joint = int(model.body_jntadr[ball])
        self.ball_q = int(model.jnt_qposadr[joint])
        self.ball_v = int(model.jnt_dofadr[joint])
        self.rail = rail
        # A front approach plane, 0.20 m ahead of the carriage, is crossed
        # before foot contact in the reference setup. It is not the goal line.
        self.plane_x = float(model.body_pos[rail.carriage, 0]) - 0.20
        self.origin_y = float(model.body_pos[rail.carriage, 1])

    def read(self, data):
        return Observation(float(data.time),
                           tuple(float(x) for x in data.qpos[self.ball_q:self.ball_q+3]),
                           tuple(float(x) for x in data.qvel[self.ball_v:self.ball_v+3]),
                           float(data.qpos[self.rail.qpos]), float(data.qvel[self.rail.dof]),
                           self.plane_x, self.origin_y, -1.0)
