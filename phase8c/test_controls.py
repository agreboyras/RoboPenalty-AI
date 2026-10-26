from bootstrap import *
import unittest
from types import SimpleNamespace
from dataclasses import dataclass
from phase8c.return_control import ReturnControl
from phase8c.sensitivity import validate_delta
from phase8c.criteria import assess

@dataclass(frozen=True)
class D:
    state:str;selected_target_m:float;command_changed:bool=False;reason:str='original'
class Fake:
    def __init__(self,state,command):
        self.d=D(state,command);self.context={'control':SimpleNamespace(position=.01,velocity=0.),'rows':[]}
    def step(self,o):self.context['rows'].append({});return self.d

class Tests(unittest.TestCase):
    def test_interception_is_exactly_unchanged(self):
        for state in ('WAITING','TRACKING','RETURNING'):
            b=Fake(state,.123);wrapper=ReturnControl(b,None)
            self.assertIs(wrapper.step(SimpleNamespace(time_s=1,keeper_q=.2,keeper_v=.1)),b.d)
    def test_done_retains_negative_feedback(self):
        b=Fake('DONE',0.);d=ReturnControl(b,None).step(SimpleNamespace(time_s=1,keeper_q=.0165,keeper_v=0.))
        self.assertEqual(d.selected_target_m,-.033);self.assertEqual(d.state,'DONE')
    def test_original_feedback_bounds(self):
        b=Fake('DONE',0.);d=ReturnControl(b,None).step(SimpleNamespace(time_s=1,keeper_q=-.7,keeper_v=-.3))
        self.assertEqual(d.selected_target_m,.12)
    def test_disabled_is_original(self):
        b=Fake('DONE',0.);self.assertIs(ReturnControl(b,None,False).step(SimpleNamespace(time_s=1,keeper_q=.02,keeper_v=0.)),b.d)
    def test_invalid_perturbations(self):
        for v in (float('nan'),float('inf'),.0051):
            with self.assertRaises(ValueError):validate_delta(v)
    def test_robustness_screen_rejects_a_single_failed_condition(self):
        r=dict(passed=True,foot_peak_n=100,fall=None,outcome='goal',plane5={'position_w':[5,1.2,.115]},sphere_post_margin_m=.185)
        grid=[{**r,'delta_y_m':v} for v in (-.005,-.002,-.001,0.,.001,.002,.005)]
        self.assertTrue(assess(grid)['passes_engineering_screen'])
        self.assertFalse(assess(grid[:-1]+[{**grid[-1],'outcome':'short_or_stopped','plane5':None}])['passes_engineering_screen'])
        self.assertFalse(assess(grid[:3])['passes_engineering_screen'])
if __name__=='__main__':unittest.main()
