"""Instantaneous constant horizontal velocity; grounded/ballistic height model."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Prediction:
    valid: bool
    reason: str
    eta_s: float | None = None
    y_w: float | None = None
    z_w: float | None = None
    rail_target_m: float | None = None
    height_model: str | None = None


def predict(observation, radius=0.115, max_horizon=3.0):
    o = observation
    numbers = (*o.ball_position_w, *o.ball_velocity_w, o.keeper_q, o.keeper_v,
               o.time_s, o.plane_x, o.rail_origin_y, o.rail_axis_y)
    if len(o.ball_position_w) != 3 or len(o.ball_velocity_w) != 3 or not all(math.isfinite(x) for x in numbers):
        return Prediction(False, 'nonfinite_or_invalid_observation')
    x, y, z = o.ball_position_w
    vx, vy, vz = o.ball_velocity_w
    if abs(o.rail_axis_y) < 1e-8:
        return Prediction(False, 'invalid_rail_axis')
    if vx <= 0.05:
        return Prediction(False, 'stationary_or_moving_away')
    if x >= o.plane_x:
        return Prediction(False, 'approach_plane_already_passed')
    eta = (o.plane_x - x) / vx
    if eta > max_horizon:
        return Prediction(False, 'outside_prediction_horizon')
    projected_y = y + vy * eta
    if z <= radius + 0.02 and abs(vz) < 0.25:
        projected_z, height_model = radius, 'rolling'
    else:
        projected_z, height_model = z + vz * eta - 0.5 * 9.81 * eta**2, 'ballistic'
        if projected_z < radius:
            # Keep a useful horizontal estimate but do not invent the vertical
            # result of a future bounce. A later observation replaces this estimate.
            q = (projected_y - o.rail_origin_y) / o.rail_axis_y
            return Prediction(True, 'horizontal_only_ground_contact_uncertain', eta,
                              projected_y, None, q, 'unknown_after_ground_contact')
    q = (projected_y - o.rail_origin_y) / o.rail_axis_y
    return Prediction(True, 'interception_estimate', eta, projected_y, projected_z, q, height_model)
