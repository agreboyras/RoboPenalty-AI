import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phase8b2.bootstrap
import unittest
from types import SimpleNamespace
from phase8b2.runtime import components
from phase4b import striker_agent as historical

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.catalog=SimpleNamespace(actions=('center','open_l','corner_r'),id='test_catalog_v1',mapping={})
        self.Runtime,self.Selector=components(self.catalog)
        module=sys.modules['phase8b2_owned_selector']
        self.observation=module.InitialObservation('long','agent',0,0,0,.2,.115,(-1,0,.115),(-2,0,.793),self.catalog.actions)
        self.cal={a:dict(kind='historical_calibration',distance='long',plane_y_w_m=y,source='confirmed_past_probe')
                  for a,y in zip(self.catalog.actions,[0,.9,-1.2])}
    def test_private_vocabulary_preserves_historical(self):
        self.assertEqual(historical.ACTIONS,('center','left','right'))
        self.assertEqual(self.observation.available_actions,self.catalog.actions)
    def test_reject_legacy_statistics(self):
        with self.assertRaises(ValueError):self.Selector(historical.StrikerAgent().snapshot())
    def test_pending_update_after_result_only(self):
        s=self.Selector();d=s.choose(self.observation,self.cal,'p1')
        self.assertEqual(len(s.snapshot()['history']),0)
        with self.assertRaises(RuntimeError):s.choose(self.observation,self.cal,'p2')
        s.observe('p1','goal');state=s.snapshot()
        self.assertEqual(state['contexts'][d['context']][d['action']]['goal'],1)
        with self.assertRaises(RuntimeError):s.observe('p1','goal')
    def test_exploration_then_updated_utility(self):
        s=self.Selector();chosen=[]
        for n in range(4):
            d=s.choose(self.observation,self.cal,str(n));chosen.append(d['action'])
            if n<3:self.assertEqual(d['reason'],'explore_untried_action')
            else:self.assertEqual(d['reason'],'maximize_updated_utility')
            s.observe(str(n),'goal' if d['action']=='corner_r' else 'save')
        self.assertEqual(set(chosen[:3]),set(self.catalog.actions))
        self.assertEqual(chosen[3],'corner_r')
    def test_seed_reproducible(self):
        a,b=self.Selector(),self.Selector()
        for n in range(7):
            x=a.choose(self.observation,self.cal,str(n),seed=2026)
            y=b.choose(self.observation,self.cal,str(n),seed=2026)
            self.assertEqual(x,y)
            a.observe(str(n),'save');b.observe(str(n),'save')
    def test_reject_future_observation(self):
        from dataclasses import replace
        with self.assertRaises(ValueError):self.Selector().choose(replace(self.observation,time_sim_s=1),self.cal,'p1')

if __name__=='__main__':unittest.main()
