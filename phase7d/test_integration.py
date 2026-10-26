"""7D presentation contracts, plus unchanged camera command namespace."""
import sys
from pathlib import Path
import queue
import threading
import unittest
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from phase7d.prototype.preview import prepared_world
from phase7d.presentation import MonumentalPresenter
from phase7d.visual_scene import StadiumScene,prepare_model
from phase7d.cameras import CameraBus,specification,VIEWS
from presentation import PresentationConfig
import mujoco
import numpy as np

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m,cls.d,_=prepared_world()

    def test_all_detail_modes_update_screen_and_fit_budget(self):
        counts=[]
        for lod in ('medium','low','none'):
            s=StadiumScene(self.m,lod);v=mujoco.MjvScene(self.m,maxgeom=2000)
            self.assertTrue(s.update_status(dict(goals=3,saves=2,penalty=5,total=5)))
            n=s.screen_updates
            self.assertFalse(s.update_status(dict(goals=3,saves=2,penalty=5,total=5)))
            self.assertEqual(s.screen_updates,n);s.populate(v)
            self.assertEqual(s.screen_state,(3,2,5,5));counts.append(len(s.primitives))
        self.assertLess(counts[1],counts[0]);self.assertLess(counts[2],counts[1])
        self.assertLess(max(counts),1500)

    def test_camera_namespace_and_epoch(self):
        q=queue.Queue(16);b=CameraBus(camera_requests=q)
        for view in VIEWS:
            self.assertTrue(b.submit('/cam '+view))
            self.assertEqual(q.get_nowait(),(0,view));self.assertIsNone(b.drain())
            self.assertIn('lookat',specification(view))
        b.submit('/cam behind','voice');self.assertIsNone(b.drain().intent)
        b.rotate();self.assertFalse(b.submit('/cam behind',generation=0))
        b.submit('Pausar partido');self.assertEqual(b.drain().intent,'pause')

    def test_presenter_owner_and_exact_update_state(self):
        def integration(d):
            a=np.empty(mujoco.mj_stateSize(self.m,mujoco.mjtState.mjSTATE_INTEGRATION))
            mujoco.mj_getState(self.m,d,a,mujoco.mjtState.mjSTATE_INTEGRATION);return a
        runtime=SimpleNamespace(model=self.m,data=self.d,engine=SimpleNamespace(mujoco=mujoco,np=np),integration_state=integration)
        p=MonumentalPresenter(runtime,PresentationConfig(),Path(__file__).parent,'long')
        before=integration(self.d)
        p.set_status(dict(goals=1,saves=2,penalty=3,total=5,phase='RESOLVING'))
        self.assertEqual(p.visual_scene.screen_state,(1,2,3,5))
        np.testing.assert_array_equal(before,integration(self.d))
        errors=[]
        def wrong_thread():
            try:p.set_status(dict(phase='READY'))
            except RuntimeError as e:errors.append(str(e))
        t=threading.Thread(target=wrong_thread);t.start();t.join()
        self.assertEqual(len(errors),1);p.close()
        self.assertTrue(p.summary()['stadium']['physical_model_unchanged'])

if __name__=='__main__':unittest.main(verbosity=2)
