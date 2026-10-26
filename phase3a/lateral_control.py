"""Deterministic commands and acceleration-limited reference; no soccer AI."""
import math
import numpy as np


class LateralControl:
    def __init__(self, limits, rail):
        self.limits, self.rail = limits, rail
        self.goal = self.position = self.velocity = self.acceleration = 0.0
        self.raw_goal = 0.0
        self.clamped_commands = 0

    def select(self, position):
        self.raw_goal = float(position)
        clipped = float(np.clip(position, -self.limits.command_travel, self.limits.command_travel))
        if clipped != position:
            self.clamped_commands += 1
        self.goal = clipped

    def advance_reference(self, dt):
        lim = self.limits
        error = self.goal - self.position
        # Stop within the remaining distance; permit a bounded direction reversal.
        desired_velocity = math.copysign(min(lim.reference_speed,
                                             math.sqrt(2 * lim.reference_acceleration * abs(error))), error) if error else 0.0
        # A small linear terminal region avoids a bang-bang oscillation at rest.
        desired_velocity = float(np.clip(3.0 * error, -abs(desired_velocity), abs(desired_velocity)))
        new_velocity = self.velocity + float(np.clip(desired_velocity - self.velocity,
                                                      -lim.reference_acceleration * dt,
                                                      lim.reference_acceleration * dt))
        self.acceleration = (new_velocity - self.velocity) / dt
        self.position += (self.velocity + new_velocity) * 0.5 * dt
        self.velocity = new_velocity
        if abs(self.position) > lim.joint_travel:
            raise AssertionError('Reference exceeded mechanical travel')

    def force(self, q, v):
        lim = self.limits
        acceleration = float(np.clip(self.acceleration + 12 * (self.position - q)
                                     + 8 * (self.velocity - v),
                                     -lim.drive_acceleration, lim.drive_acceleration))
        if v >= lim.velocity_guard:
            acceleration = min(acceleration, -lim.drive_acceleration)
        elif v <= -lim.velocity_guard:
            acceleration = max(acceleration, lim.drive_acceleration)
        # Viscous compensation and force-limited servo; contact remains physical.
        return float(np.clip(self.rail.carried_mass * acceleration + self.rail.damping * v,
                             -lim.force, lim.force))


def schedule(case):
    return {
        'center': [(0.0, 0.0)],
        'left': [(0.0, 0.0), (1.0, 0.60)],
        'right': [(0.0, 0.0), (1.0, -0.60)],
        'return': [(0.0, 0.0), (1.0, 0.60), (6.0, 0.0)],
        'moving_contact': [(0.0, 0.0), (4.1, 0.60)],
        'limits': [(0.0, 0.0), (1.0, 99.0), (8.0, -99.0)],
        'manual': [(0.0, 0.0)],
    }[case]
