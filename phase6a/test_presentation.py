"""Behavioral presentation tests; fake handle is not evidence of GUI availability."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from presentation import Presenter,PresentationConfig,ViewerClosed,ViewerPhysicsChange

class FakeHandle:
    def __init__(self):self.running=True;self.modify=lambda:None;self.text=None;self.syncs=0
    def is_running(self):return self.running
    def set_texts(self,text):self.text=text
    def sync(self,state_only=False):self.syncs+=1;self.modify()
    def close(self):self.running=False

def presenter():
    data=SimpleNamespace(time=0.,qpos=np.zeros(1))
    model=SimpleNamespace(opt=SimpleNamespace(timestep=.002,gravity=np.array([0.,0.,-9.81])))
    mj=SimpleNamespace(mjtFontScale=SimpleNamespace(mjFONTSCALE_100=100),mjtGridPos=SimpleNamespace(mjGRID_TOPLEFT=0))
    runtime=SimpleNamespace(data=data,model=model,rail=SimpleNamespace(qpos=0),engine=SimpleNamespace(mujoco=mj,np=np))
    runtime.integration_state=lambda d:np.array([d.time,d.qpos[0]])
    p=Presenter(runtime,PresentationConfig(realtime=False),Path(__file__).resolve().parent,'long')
    p.handle=FakeHandle();p.launch_model_id=id(model);p.launch_data_id=id(data)
    return p

class PresentationTests(unittest.TestCase):
    def test_config_rejects_negative_pause(self):
        with self.assertRaises(ValueError):PresentationConfig(before_shot_s=-1)
    def test_config_rejects_zero_fps(self):
        with self.assertRaises(ValueError):PresentationConfig(fps=0)
    def test_config_rejects_nonfinite(self):
        with self.assertRaises(ValueError):PresentationConfig(end_s=float('nan'))
    def test_sync_preserves_state(self):
        p=presenter();p.sync();self.assertEqual(p.guard_checks,1);self.assertEqual(p.runtime.data.qpos[0],0)
    def test_state_edit_aborts_without_undoing(self):
        p=presenter();p.handle.modify=lambda:p.runtime.data.qpos.fill(.2)
        with self.assertRaises(ViewerPhysicsChange):p.sync()
        self.assertEqual(p.runtime.data.qpos[0],.2)
    def test_physics_option_edit_aborts(self):
        p=presenter();p.handle.modify=lambda:setattr(p.runtime.model.opt,'timestep',.01)
        with self.assertRaises(ViewerPhysicsChange):p.sync()
    def test_pause_does_not_advance_simulation(self):
        p=presenter();p.pause('test',.01)
        self.assertEqual(p.runtime.data.time,0)
        self.assertTrue(p.pauses[-1]['physics_unchanged'])
        self.assertGreaterEqual(p.pauses[-1]['wall_s'],.01)
    def test_headless_skips_presentation_pauses(self):
        p=presenter();p.handle=None;p.pause('test',999)
        self.assertEqual(p.pauses,[])
    def test_closed_viewer_cancels(self):
        p=presenter();p.handle.close()
        with self.assertRaises(ViewerClosed):p.sync()
    def test_finally_close_is_observable(self):
        p=presenter();p.close();self.assertTrue(p.closed);self.assertFalse(p.handle.is_running())
    def test_frame_gate_does_not_add_steps(self):
        p=presenter();p.begin_episode();p.runtime.data.time=.002;p.after_step();n=p.frames
        p.runtime.data.time=.004;p.after_step();self.assertEqual(p.frames,n)
        p.runtime.data.time=.04;p.after_step();self.assertEqual(p.frames,n+1)
    def test_overlay_has_goal_and_actual_keeper_position(self):
        p=presenter();p.goal_q=-.12;p.runtime.data.qpos[0]=-.03
        p.set_status({'penalty':2,'total':5,'goals':1,'saves':1,'misses':0,'phase':'SHOOTING','action':'right'})
        p.sync();self.assertIn('-0.120',p.handle.text[3]);self.assertIn('-0.030',p.handle.text[3])

if __name__=='__main__':unittest.main(verbosity=2)
