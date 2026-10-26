import unittest
from bootstrap import *
from phase8b1.planners import stopping_interval,InterceptionPlanner,servo_rollout,LoggedPlanner
from lateral_scene import Limits
from observations import Observation
from agent import GoalkeeperAgent
from lateral_control import LateralControl
from types import SimpleNamespace

class Tests(unittest.TestCase):
    def observation(self,t=0.,y=.4,vx=5.,q=0.,v=0.):return Observation(t,(0.,y,.115),(vx,0.,0.),q,v)
    def snapshot(self):return dict(reference_q=0.,reference_v=0.,reference_a=0.,mass=35.,damping=70.)
    def test_rest_reach_and_braking(self):
        lim=Limits();interval,ok=stopping_interval(0,0,1,lim)
        self.assertTrue(ok);self.assertAlmostEqual(interval[1],.125)
        self.assertAlmostEqual(interval[0],-.125)
        interval,ok=stopping_interval(0,.3,.1,lim)
        self.assertFalse(ok);self.assertAlmostEqual(interval[0],.0275)
    def test_rollout_does_not_change_reference_snapshot(self):
        snap=self.snapshot();old=dict(snap)
        q,v=servo_rollout(.65,self.observation(),.6,Limits(),snap)
        self.assertEqual(snap,old);self.assertGreater(q,0);self.assertLess(v,.4)
    def test_wait_detection_hold_and_return(self):
        for variant in ('B','C'):
            p=InterceptionPlanner(Limits(),variant,self.snapshot)
            self.assertEqual(p.step(self.observation(0,vx=0)).selected_target_m,0)
            self.assertEqual(p.step(self.observation(.02)).state,'WAITING')
            d=p.step(self.observation(.04));self.assertEqual(d.state,'TRACKING')
            self.assertLess(d.selected_target_m,0);self.assertLessEqual(abs(d.selected_target_m),.65)
            d=p.step(Observation(.06,(4.2,.4,.115),(-1.,0.,0.),-.02,-.1))
            self.assertEqual(d.state,'RETURNING');self.assertGreater(d.selected_target_m,0)
            self.assertLessEqual(abs(d.selected_target_m),.12)
    def test_B_does_not_shrink_with_eta_alone(self):
        p=InterceptionPlanner(Limits(),'B',self.snapshot)
        p.step(self.observation(0));first=p.step(self.observation(.02)).selected_target_m
        last=p.step(Observation(.2,(3.9,.4,.115),(5.,0.,0.),-.01,-.02)).selected_target_m
        self.assertAlmostEqual(first,last)
    def test_A_is_exact_historical_agent(self):
        control=LateralControl(Limits(),SimpleNamespace(carried_mass=35,damping=70))
        ctx=dict(rows=[],control=control);logged=LoggedPlanner(Limits(),'A',ctx);old=GoalkeeperAgent(Limits())
        for n in range(10):
            o=self.observation(n*.02)
            self.assertEqual(logged.step(o),old.step(o))
        self.assertEqual(len(ctx['rows']),10)
    def test_causal_replay_and_bounds(self):
        for variant in ('B','C'):
            a=InterceptionPlanner(Limits(),variant,self.snapshot);b=InterceptionPlanner(Limits(),variant,self.snapshot)
            for n in range(15):
                o=self.observation(n*.02,y=10.)
                d=a.step(o);self.assertEqual(d,b.step(o));self.assertLessEqual(abs(d.selected_target_m),.65)
    def test_invalid_input_returns_safe_command(self):
        for variant in ('B','C'):
            p=InterceptionPlanner(Limits(),variant,self.snapshot)
            d=p.step(self.observation(0,y=float('nan')))
            self.assertEqual(d.selected_target_m,0)
            d=p.step(self.observation(.02,q=float('nan')))
            self.assertEqual(d.selected_target_m,0)

if __name__=='__main__':unittest.main(verbosity=2)
