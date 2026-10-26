"""Real runtime reset test with deliberately contaminated in-memory state."""
import contextlib
import io
import unittest
from runtime import SimulationRuntime

class ResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):cls.runtime=SimulationRuntime()
    def test_mujoco_and_freekick_restore_after_contamination(self):
        r=self.runtime
        r.data.time=9.
        r.data.qpos[:]+=0.1;r.data.qvel[:]=3;r.data.ctrl[:]=12
        r.data.qacc_warmstart[:]=5;r.data.qfrc_applied[:]=7;r.data.xfrc_applied[:]=8
        r.kick.sensor_updates=999;r.kick.fixed_requested=True;r.kick.kick_requested=True
        r.kick.fsm.freekick_policy.time_step=999
        r.kick.fsm.freekick_policy.last_action_il[:]=5
        r.kick.fsm.freekick_policy._ball_pos_buf[-1][:]=7
        r.kick.fsm.fixed_pose_1.cur_step=999
        r.kick.state.target_y_bias=123
        r.reset_scene();r.reset_adapter()
        self.assertTrue(r.resets[-1]['full_integration_state_equal_to_fresh'])
        self.assertTrue(r.resets[-1]['contacts_equal_to_fresh'])
        self.assertTrue(r.resets[-1]['freekick_state_equal_to_pristine'])
        self.assertTrue(r.resets[-1]['onnx_session_identity_preserved'])
        self.assertEqual(r.kick.state.target_y_bias,0)
        self.assertEqual(r.kick.fsm.fixed_pose_1.cur_step,0)

if __name__=='__main__':unittest.main(verbosity=2)
