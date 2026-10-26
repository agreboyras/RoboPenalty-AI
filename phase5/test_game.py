"""Synthetic game-flow tests, separate from physical acceptance runs."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from game import Config,Match,Phase,Scoreboard
from test_striker import observation,calibration

class FakePhysics:
    def __init__(self,labels=None):self.labels=list(labels or ['save','goal','save','goal','goal']); self.calls=0
    def execute(self,distance,opponent,output,choose,shooting):
        obs=observation(distance=distance,opponent=opponent)
        action=choose(obs);shooting();label=self.labels[self.calls];self.calls+=1
        return ({'_synthetic_label':label,'rail':{'final_q_m':0},'simulated_s':14,
            'initial_state_sha256':'synthetic_fixture','evaluation':{'first_foot_ball':None,'first_keeper_ball':None}},
            {'action':action,'scenario':'synthetic_fixture'},0.01)
    def evaluate(self,result,*args):return result['_synthetic_label'],0
    def summary(self):return {'fixture':'no_physical_claim','calls':self.calls}

class GameTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parent/'results';root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.folder=Path(self.temp.name).resolve()
        assert self.folder.is_relative_to(root.resolve())
    def tearDown(self):self.temp.cleanup()
    def game(self,config=Config(),labels=None):
        return Match(config,FakePhysics(labels),self.folder,calibration=calibration(config.distance),printer=lambda *a,**k:None)
    def test_five_penalties_finish_and_score(self):
        g=self.game();r=g.play()
        self.assertEqual(r['phase'],'FINISHED')
        self.assertEqual((g.score.goals,g.score.saves,g.score.misses),(3,2,0))
        self.assertEqual(len(g.score.history),5)
    def test_each_penalty_has_expected_states(self):
        r=self.game().play()
        for n in range(1,6):
            phases=[x['phase'] for x in r['transitions'] if x['penalty']==n]
            self.assertEqual(phases,['PREPARING','SHOOTING','RESOLVING','FINISHED' if n==5 else 'READY'])
    def test_learning_persists(self):
        r=self.game().play();s=r['striker_statistics']
        self.assertEqual(len(s['history']),5)
        self.assertIsNone(s['pending'])
        self.assertEqual(sum(sum(x.values()) for c in s['contexts'].values() for x in c.values()),5)
    def test_selection_uses_only_previous_feedback(self):
        g=self.game();r=g.play()
        self.assertEqual([x['action'] for x in r['scoreboard']['history']],['left','right','center','right','right'])
    def test_quantity_can_change(self):
        g=self.game(Config(penalties=2));self.assertEqual(len(g.play()['scoreboard']['history']),2)
    def test_miss_increments_only_miss(self):
        g=self.game(Config(penalties=1),['miss']);g.play()
        self.assertEqual((g.score.goals,g.score.saves,g.score.misses),(0,0,1))
    def test_unresolved_does_not_score_or_learn(self):
        g=self.game(Config(penalties=1),['unresolved'])
        with self.assertRaises(ValueError):g.play()
        self.assertEqual(g.score.history,[])
        self.assertEqual(g.selector.state['history'],[])
    def test_match_cannot_run_twice(self):
        g=self.game();g.play()
        with self.assertRaises(RuntimeError):g.play()
    def test_illegal_transition_rejected(self):
        with self.assertRaises(RuntimeError):self.game().transition(Phase.FINISHED)
    def test_score_rejects_duplicate(self):
        s=Scoreboard();s.record({'penalty':1,'outcome':'goal'})
        with self.assertRaises(ValueError):s.record({'penalty':1,'outcome':'save'})
        self.assertEqual(s.goals,1)
    def test_invalid_quantity_rejected(self):
        with self.assertRaises(ValueError):Config(penalties=0)
    def test_configuration_modes_accepted(self):
        self.assertEqual(Config(keeper='fixed',striker='random',distance='original').keeper,'fixed')
    def test_fixed_striker_stays_fixed(self):
        r=self.game(Config(striker='fixed',fixed_action='left')).play()
        self.assertTrue(all(x['action']=='left' for x in r['scoreboard']['history']))

if __name__=='__main__':unittest.main(verbosity=2)
