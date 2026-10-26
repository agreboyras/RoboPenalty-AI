from bootstrap import *
import unittest
from types import SimpleNamespace
import numpy as np
import json
from phase8b3.posture import direction,PosturePD

class Tests(unittest.TestCase):
    def test_direction_causal_coordinates(self):
        obs=SimpleNamespace(rail_origin_y=0.,keeper_q=.2)
        for y,want in [(.6,'LEFT'),(-.6,'RIGHT'),(-.2,'CENTER')]:
            d=SimpleNamespace(state='TRACKING',prediction=dict(valid=True,y_w=y))
            self.assertEqual(direction(d,obs),want)
    def test_invalid_hold_and_recovery(self):
        obs=SimpleNamespace(rail_origin_y=0.,keeper_q=0.)
        self.assertEqual(direction(SimpleNamespace(state='TRACKING',prediction={'valid':False}),obs,'LEFT'),'LEFT')
        self.assertEqual(direction(SimpleNamespace(state='RETURNING'),obs),'WAIT')
    def test_hysteresis(self):
        obs=SimpleNamespace(rail_origin_y=0.,keeper_q=0.)
        d=SimpleNamespace(state='TRACKING',prediction=dict(valid=True,y_w=.13))
        self.assertEqual(direction(d,obs,'LEFT'),'LEFT')
    def test_reference_filter_limits(self):
        rows=json.loads((HERE/'results/audit.json').read_text())['joints']
        model=SimpleNamespace(joint=lambda j:SimpleNamespace(name=rows[j]['name']),geom=lambda n:SimpleNamespace(id=0),
            opt=SimpleNamespace(timestep=.002),jnt_range=np.tile([-3.,3.],(29,1)),jnt_actfrcrange=np.tile([-120.,120.],(29,1)))
        keeper=SimpleNamespace(joints=np.arange(29),qpos=np.arange(29),dofs=np.arange(29),pelvis=0,geoms=[])
        rail=SimpleNamespace(qpos=29,carriage=1)
        data=SimpleNamespace(time=0.,qpos=np.zeros(30),qvel=np.zeros(30),qfrc_actuator=np.zeros(30),
            xpos=np.array([[4.2,0,.793],[4.2,0,0]]),contact=[],ncon=0,ctrl=np.zeros(59))
        base=np.array([r['initial_reference_rad'] for r in rows]);pd=PosturePD(model,keeper,rail)
        previous=np.zeros(29)
        for n in range(5000):
            data.time=n*.002
            state='TRACKING' if n<2500 else 'RETURNING'
            y=.6 if n<1200 else -.6
            pd.notify(SimpleNamespace(state=state,prediction=dict(valid=True,y_w=y)),SimpleNamespace(rail_origin_y=0.,keeper_q=0.))
            pd.command(data,base,np.full(29,120.))
            self.assertLessEqual(abs(pd.velocity).max(),.6+1e-12)
            self.assertLessEqual(abs(pd.velocity-previous).max()/.002,1.5+1e-10)
            previous=pd.velocity.copy()
        self.assertLess(abs(pd.reference-pd.target(base)).max(),.001)
if __name__=='__main__':unittest.main()
