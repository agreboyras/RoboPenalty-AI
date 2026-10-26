"""Owned initial conditions only; no third-party code, model or policy is copied."""
import math
import numpy as np

SCENARIOS = {
    'center': {},
    'preset_left': {'target_bias': 0.75},
    'preset_right': {'target_bias': -0.50},
    'ball_left': {'ball_delta_y': 0.05},
    'ball_right': {'ball_delta_y': -0.05},
    'yaw_left': {'yaw': 0.08},
    'yaw_right': {'yaw': -0.08},
    'offset_left': {'translate_y': 0.45},
    'offset_right': {'translate_y': -0.45},
    'long_center': {'translate_x': -2.0},
    'long_left': {'translate_x': -2.0, 'translate_y': 0.45},
    'long_right': {'translate_x': -2.0, 'translate_y': -0.45},
    'long_preset_left': {'translate_x': -2.0, 'target_bias': 0.75},
    'long_preset_right': {'translate_x': -2.0, 'target_bias': -0.50},
    'offset_far_left': {'translate_y': 2.0},
    'ball_far_left': {'ball_delta_y': 0.40},
    'miss_far_left': {'translate_y': 4.0},
}


def initialize(config, model, data, kick, rail, probe=False):
    """Called exactly once, before stepping. Ball velocity is never assigned."""
    ball_q = int(model.jnt_qposadr[int(model.body_jntadr[model.body('ball').id])])
    # Scene's actual joint name is resolved by its body, avoiding name guesses.
    root = kick.root_q
    yaw = config.get('yaw', 0.0)
    c, s = math.cos(yaw), math.sin(yaw)
    origin = data.qpos[root:root+3].copy()
    relative = data.qpos[ball_q:ball_q+3] - origin
    data.qpos[ball_q:ball_q+2] = origin[:2] + np.array([c*relative[0]-s*relative[1], s*relative[0]+c*relative[1]])
    data.qpos[root+3:root+7] = [math.cos(yaw/2),0,0,math.sin(yaw/2)]
    shift = np.array([config.get('translate_x',0.0),config.get('translate_y',0.0)])
    data.qpos[root:root+2] += shift
    data.qpos[ball_q:ball_q+2] += shift
    data.qpos[ball_q+1] += config.get('ball_delta_y',0.0)
    kick.state.target_y_bias = config.get('target_bias',0.0)
    if probe:
        model.body_pos[rail.carriage,1] = 8.0
