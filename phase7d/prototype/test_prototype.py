"""Prototype-only checks; no policy loading, stepping or game changes."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from phase7c.preview import prepared_world
from phase7c.integrity import model_signature
from phase7d.prototype.stadium import BowlScene,prepare,crowd_pixels
import mujoco

class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m,cls.d,_=prepared_world()

    def test_model_and_complete_integration_state(self):
        m,d=self.m,self.d
        before=model_signature(m)
        state=np.empty(mujoco.mj_stateSize(m,mujoco.mjtState.mjSTATE_INTEGRATION))
        mujoco.mj_getState(m,d,state,mujoco.mjtState.mjSTATE_INTEGRATION)
        prepare(m);s=BowlScene(m)
        visual=mujoco.MjvScene(m,maxgeom=2000);s.populate(visual)
        after=np.empty_like(state);mujoco.mj_getState(m,d,after,mujoco.mjtState.mjSTATE_INTEGRATION)
        self.assertEqual(before,model_signature(m));np.testing.assert_array_equal(state,after)
        self.assertEqual(int(m.nlight),2)

    def test_geometry_budget_and_location(self):
        s=BowlScene(self.m)
        self.assertLess(len(s.primitives),1500)
        self.assertEqual(len(s.crowd),120)
        for p in s.primitives:
            if p.name in s.crowd:
                x,y,_=p.position
                self.assertTrue(x>5 or abs(y)>12)
        for matrix in s.rotations.values():
            r=matrix.reshape(3,3)
            np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-14)
            self.assertAlmostEqual(float(np.linalg.det(r)),1)

    def test_visual_capacity_rejection(self):
        s=BowlScene(self.m);v=mujoco.MjvScene(self.m,maxgeom=10)
        with self.assertRaises(RuntimeError):s.populate(v)

    def test_score_contract_and_decoration_off(self):
        s=BowlScene(self.m);static=list(s.static)
        s.update_status(dict(goals=3,saves=2,penalty=5,total=5))
        self.assertEqual(s.static,static)
        self.assertTrue(any(p.name.startswith('screen_score') for p in s.primitives))
        other=BowlScene(self.m,False)
        self.assertFalse(any(p.name.startswith('screen_') for p in other.primitives))

    def test_pattern_determinism_without_global_rng_effect(self):
        np.random.seed(99);expected=np.random.random(3)
        np.random.seed(99);a=crowd_pixels();actual=np.random.random(3)
        np.testing.assert_array_equal(expected,actual)
        np.testing.assert_array_equal(a,crowd_pixels())
        self.assertEqual(a.shape,(3072,512,3));self.assertEqual(a.dtype,np.uint8)

if __name__=='__main__':unittest.main(verbosity=2)
