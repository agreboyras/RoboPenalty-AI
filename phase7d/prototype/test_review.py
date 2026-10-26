"""Review checks, independent of simulation and game controls."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from phase7d.prototype.preview import prepared_world,model_signature
from phase7d.prototype.stadium import BowlScene,prepare
from phase7d.prototype.revision import RevisedBowl,prepare_revision,crowd_faces,face_basis
from phase7d.prototype.review import state
import mujoco

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m,cls.d,_=prepared_world()

    def test_six_distinct_deterministic_faces_no_global_rng(self):
        np.random.seed(811);expected=np.random.random(4)
        np.random.seed(811);pixels=crowd_faces()
        np.testing.assert_array_equal(expected,np.random.random(4))
        np.testing.assert_array_equal(pixels,crowd_faces())
        self.assertEqual(pixels.shape,(3072,512,3));self.assertEqual(pixels.dtype,np.uint8)
        self.assertEqual(len({pixels[i*512:(i+1)*512].tobytes() for i in range(6)}),6)

    def test_same_bowl_dimensions_and_small_geometry_increase(self):
        old=BowlScene(self.m);new=RevisedBowl(self.m)
        self.assertEqual(old.crowd,new.crowd)
        before={p.name:p for p in old.primitives if p.name in old.rotations}
        after={p.name:p for p in new.primitives if p.name in new.rotations}
        self.assertEqual(before,after)
        self.assertEqual(len(new.primitives)-len(old.primitives),8)
        self.assertLess(len(new.primitives),1500)
        self.assertEqual(set(new.faces.values()),set(range(6)))

    def test_face_mapping_preserves_box_volume_and_orientation(self):
        size=np.array([1.1,3.4,.035])
        for face in range(6):
            b=face_basis(face)
            np.testing.assert_array_equal(b.T@b,np.eye(3))
            self.assertEqual(round(np.linalg.det(b)),1)
            newsize=np.abs(b).T@size
            np.testing.assert_allclose(b@np.diag(newsize**2)@b.T,np.diag(size**2))

    def test_render_geometry_does_not_change_model_or_full_state(self):
        m,d=self.m,self.d;sig=model_signature(m);before=state(m,d)
        prepare_revision(m);s=RevisedBowl(m)
        v=mujoco.MjvScene(m,maxgeom=2000);s.populate(v)
        s.update_status(dict(goals=3,saves=2,penalty=5,total=5));s.populate(v)
        self.assertEqual(sig,model_signature(m));self.assertEqual(before,state(m,d))
        self.assertEqual(len(s.crowd),120)

if __name__=='__main__':unittest.main(verbosity=2)
