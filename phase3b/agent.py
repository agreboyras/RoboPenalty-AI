"""Goal-based goalkeeper: wait, track a causal prediction, return to center."""
from dataclasses import dataclass, asdict
import math

from predictor import predict


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def reachable_interval(q, velocity, seconds, vmax, acceleration, travel):
    """Kinematic estimate, not a guarantee of the PD plant's arrival time."""
    h = max(0.0, seconds)
    v = clip(velocity, -vmax, vmax)
    def displacement(initial):
        to_cap = (vmax - initial) / acceleration
        t = min(h, to_cap)
        return initial * t + 0.5 * acceleration * t*t + vmax * (h-t)
    lower = clip(q - displacement(-v), -travel, travel)
    upper = clip(q + displacement(v), -travel, travel)
    return min(lower, upper), max(lower, upper)


@dataclass(frozen=True)
class Decision:
    time_s: float
    state: str
    reason: str
    prediction: dict
    selected_target_m: float
    reachable: bool | None
    reachable_interval_m: tuple | None
    command_changed: bool


class GoalkeeperAgent:
    def __init__(self, limits):
        self.limits = limits
        self.state = 'WAITING'
        self.target = 0.0
        self.filtered = None
        self.evidence_count = 0
        self.detection_time = None
        self.first_command_time = None
        self.episode_end_time = None
        self.first_prediction = None
        self.previous_time = None
        self.last_update = -math.inf
        self.slow_since = None
        self.passed_since = None

    def step(self, observation):
        o = observation
        p = predict(o)
        if p.reason in ['nonfinite_or_invalid_observation', 'invalid_rail_axis']:
            self.state, self.target = 'RETURNING', 0.0
            return Decision(o.time_s, self.state, p.reason, asdict(p), 0.0, None, None, True)
        if self.previous_time is not None and o.time_s <= self.previous_time:
            raise ValueError('Agent requires strictly increasing observation times')
        self.previous_time = o.time_s
        old_target = self.target
        reached, interval = None, None
        reason = p.reason
        if self.state in ['RETURNING', 'DONE']:
            self.target = 0.0
            if abs(o.keeper_q) < 0.01 and abs(o.keeper_v) < 0.02:
                self.state = 'DONE'
            reason = 'episode_finished_return_center'
        elif self.state == 'WAITING':
            evidence = p.valid and o.ball_velocity_w[0] >= 0.8
            self.evidence_count = self.evidence_count + 1 if evidence else 0
            self.target = 0.0
            if self.evidence_count >= 2:
                self.state = 'TRACKING'
                self.detection_time = o.time_s
                self.first_prediction = asdict(p)
                reason = 'shot_detected_two_observations'
            else:
                reason = 'waiting_for_shot_evidence'
        if self.state == 'TRACKING':
            x, y, z = o.ball_position_w
            vx, vy, vz = o.ball_velocity_w
            if abs(vx) < 0.15:
                self.slow_since = o.time_s if self.slow_since is None else self.slow_since
            else:
                self.slow_since = None
            if x >= o.plane_x:
                self.passed_since = o.time_s if self.passed_since is None else self.passed_since
            if (vx < -0.2 or x >= 5.115 or
                (self.slow_since is not None and o.time_s-self.slow_since >= 0.3) or
                (self.passed_since is not None and o.time_s-self.passed_since >= 0.5)):
                self.state, self.target = 'RETURNING', 0.0
                self.episode_end_time = o.time_s
                reason = 'observed_rebound_goal_or_stopped_ball'
            elif p.valid:
                self.filtered = p.rail_target_m if self.filtered is None else 0.35*p.rail_target_m + 0.65*self.filtered
                bounded = clip(self.filtered, -self.limits.command_travel, self.limits.command_travel)
                # Allow 50 ms for observation/plant response. Reachability is estimated
                # from CURRENT position and velocity, never a rollout of future MuJoCo.
                interval = reachable_interval(o.keeper_q, o.keeper_v, p.eta_s-0.05,
                                              self.limits.reference_speed,
                                              self.limits.reference_acceleration,
                                              self.limits.command_travel)
                reached = interval[0] <= self.filtered <= interval[1] and abs(self.filtered) <= self.limits.command_travel
                best = clip(bounded, *interval)
                if o.time_s-self.last_update >= 0.06 and abs(best-self.target) >= 0.01:
                    self.target, self.last_update = best, o.time_s
                if self.first_command_time is None and abs(self.target) >= 0.01:
                    self.first_command_time = o.time_s
                reason = 'track_reachable_target' if reached else 'best_effort_unreachable_target'
            else:
                # Hold while a bounce/floor interaction makes prediction invalid.
                # Next observation is predicted afresh; no final trajectory is stored.
                reason = 'hold_until_prediction_valid:' + p.reason
        return Decision(o.time_s, self.state, reason, asdict(p), self.target,
                        reached, interval, self.target != old_target)
