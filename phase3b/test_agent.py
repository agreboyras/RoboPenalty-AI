"""Deterministic varied trajectories. These tests do not import MuJoCo/policies."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from observations import Observation
from predictor import predict
from agent import GoalkeeperAgent, reachable_interval


LIMITS = SimpleNamespace(command_travel=0.65, reference_speed=0.30, reference_acceleration=0.50)


def obs(t=0.0, position=(1.0, 0.0, 0.115), velocity=(3.0, 0.0, 0.0), q=0.0, v=0.0):
    return Observation(t, position, velocity, q, v)


class PredictorTests(unittest.TestCase):
    def test_center_and_time(self):
        p = predict(obs())
        self.assertTrue(p.valid)
        self.assertEqual((p.eta_s, p.y_w, p.z_w, p.rail_target_m), (1.0, 0.0, 0.115, -0.0))

    def test_both_lateral_directions_and_different_speeds(self):
        for vx in [1.0, 2.0, 5.0, 10.0]:
            for vy in [-0.8, -0.2, 0.2, 0.8]:
                with self.subTest(vx=vx, vy=vy):
                    p = predict(obs(velocity=(vx, vy, 0)))
                    self.assertTrue(p.valid)
                    self.assertAlmostEqual(p.y_w, vy*3/vx)
                    self.assertAlmostEqual(p.rail_target_m, -p.y_w)

    def test_zero_and_away(self):
        for vx in [0, -1, -10]:
            self.assertFalse(predict(obs(velocity=(vx, 0, 0))).valid)

    def test_already_crossed(self):
        self.assertEqual(predict(obs(position=(4.1, 0, 0.115))).reason, 'approach_plane_already_passed')

    def test_long_horizon(self):
        self.assertEqual(predict(obs(velocity=(0.1, 0, 0))).reason, 'outside_prediction_horizon')

    def test_slow_nearby_ball(self):
        p = predict(obs(position=(3.8, 0, 0.115), velocity=(0.2, 0, 0)))
        self.assertTrue(p.valid)
        self.assertAlmostEqual(p.eta_s, 1.0)

    def test_airborne_ballistic_height(self):
        p = predict(obs(position=(3.0, 0.2, 1.0), velocity=(5.0, -0.1, 1.0)))
        self.assertTrue(p.valid)
        self.assertAlmostEqual(p.z_w, 1.0 + 0.2 - 0.5*9.81*0.2**2)
        self.assertEqual(p.height_model, 'ballistic')

    def test_future_floor_contact_is_not_invented(self):
        p = predict(obs(position=(1, 0, 0.5), velocity=(3, 0, 0)))
        self.assertTrue(p.valid)
        self.assertIsNone(p.z_w)
        self.assertEqual(p.height_model, 'unknown_after_ground_contact')
        self.assertEqual(p.y_w, 0.0)

    def test_rebound_recomputes_from_present(self):
        before = predict(obs(position=(3, 0, 0.115), velocity=(3, 0.5, 0)))
        after = predict(obs(position=(3, 0, 0.115), velocity=(3, -0.5, 0)))
        self.assertAlmostEqual(before.y_w, -after.y_w)
        self.assertFalse(predict(obs(velocity=(-3, 0.5, 0))).valid)

    def test_nonfinite(self):
        self.assertFalse(predict(obs(velocity=(float('nan'), 0, 0))).valid)

    def test_rail_origin_and_sign(self):
        p = predict(replace(obs(), rail_origin_y=0.2))
        self.assertAlmostEqual(p.rail_target_m, 0.2)


class AgentTests(unittest.TestCase):
    def detect(self, agent, position=(2, -0.2, 0.115), velocity=(2, 0, 0)):
        agent.step(obs(0.0, position, velocity))
        return agent.step(obs(0.02, position, velocity))

    def test_wait_without_motion(self):
        a = GoalkeeperAgent(LIMITS)
        for t in [0, 1, 2, 3]:
            d = a.step(obs(t, velocity=(0, 0, 0)))
            self.assertEqual((d.state, d.selected_target_m), ('WAITING', 0.0))

    def test_requires_two_consecutive_samples(self):
        a = GoalkeeperAgent(LIMITS)
        self.assertEqual(a.step(obs()).state, 'WAITING')
        self.assertEqual(a.step(obs(0.02)).state, 'TRACKING')

    def test_single_spike_does_not_trigger(self):
        a = GoalkeeperAgent(LIMITS)
        a.step(obs())
        a.step(obs(0.02, velocity=(0, 0, 0)))
        self.assertEqual(a.step(obs(0.04)).state, 'WAITING')

    def test_selects_opposite_targets(self):
        for y in [-0.15, 0.15]:
            a = GoalkeeperAgent(LIMITS)
            d = self.detect(a, position=(2, y, 0.115))
            self.assertLess(d.selected_target_m*y, 0)
            self.assertTrue(d.reachable)

    def test_unreachable_shot_best_effort(self):
        a = GoalkeeperAgent(LIMITS)
        d = self.detect(a, position=(3.8, -0.6, 0.115), velocity=(5, 0, 0))
        self.assertFalse(d.reachable)
        self.assertEqual(d.selected_target_m, 0.0)
        self.assertLessEqual(abs(d.selected_target_m), 0.65)

    def test_travel_limit_even_with_longer_horizon(self):
        a = GoalkeeperAgent(LIMITS)
        d = self.detect(a, position=(1, -3, 0.115), velocity=(1, 0, 0))
        self.assertFalse(d.reachable)
        self.assertLessEqual(abs(d.selected_target_m), 0.65)

    def test_small_prediction_jitter_does_not_change_command(self):
        a = GoalkeeperAgent(LIMITS)
        first = self.detect(a)
        for n in range(2, 20):
            d = a.step(obs(n*0.02, position=(2, -0.2 + (-1)**n*0.002, 0.115), velocity=(2, 0, 0)))
            self.assertEqual(d.selected_target_m, first.selected_target_m)

    def test_rebound_returns_center(self):
        a = GoalkeeperAgent(LIMITS)
        self.detect(a)
        d = a.step(obs(0.04, velocity=(-2, 0, 0), q=0.1))
        self.assertEqual((d.state, d.selected_target_m), ('RETURNING', 0.0))
        self.assertEqual(a.step(obs(0.06, velocity=(-2, 0, 0))).state, 'DONE')

    def test_lateral_rebound_updates_goal_while_still_incoming(self):
        a = GoalkeeperAgent(LIMITS)
        first = self.detect(a)
        self.assertGreater(first.selected_target_m, 0)
        for t in [0.04, 0.06, 0.08, 0.10]:
            changed = a.step(obs(t, position=(2, -0.2, 0.115), velocity=(2, 1.0, 0)))
        self.assertEqual(changed.state, 'TRACKING')
        self.assertLess(changed.selected_target_m, 0)

    def test_observed_goal_finishes_episode(self):
        a = GoalkeeperAgent(LIMITS)
        self.detect(a)
        self.assertEqual(a.step(obs(0.04, position=(5.2, 0, 0.115))).state, 'RETURNING')

    def test_crossed_approach_plane_holds_then_returns(self):
        a = GoalkeeperAgent(LIMITS)
        self.detect(a)
        self.assertEqual(a.step(obs(0.04, position=(4.1, 0, 0.115))).state, 'TRACKING')
        self.assertEqual(a.step(obs(0.60, position=(4.1, 0, 0.115))).state, 'RETURNING')

    def test_timestamp_order(self):
        a = GoalkeeperAgent(LIMITS)
        a.step(obs())
        with self.assertRaises(ValueError):
            a.step(obs())

    def test_invalid_observation_returns_safe_target(self):
        a = GoalkeeperAgent(LIMITS)
        self.detect(a)
        d = a.step(obs(0.04, velocity=(float('nan'), 0, 0)))
        self.assertEqual(d.selected_target_m, 0)

    def test_reachability_includes_acceleration_and_current_velocity(self):
        lo, hi = reachable_interval(0, 0, 0.2, 0.3, 0.5, 0.65)
        self.assertAlmostEqual(hi, 0.01)
        self.assertAlmostEqual(lo, -0.01)
        lo2, hi2 = reachable_interval(0, 0.2, 0.2, 0.3, 0.5, 0.65)
        self.assertGreater(hi2, hi)
        self.assertGreater(lo2, lo)


if __name__ == '__main__':
    unittest.main(verbosity=2)
