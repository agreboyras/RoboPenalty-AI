import unittest
from evaluation import classify, interpolate_q, min_center_travel_time

def trial(goal=False,contact=False,foot=True,cross=True):
    return {'evaluation':{'first_foot_ball': {'time':1} if foot else None,
                         'foot_peak_force_n':100 if foot else 0,
                         'goal_detected':goal,'first_keeper_ball':{'time':1} if contact else None,
                         'keeper_peak_contact_force_n':100 if contact else 0,
                         'goal_crossing_measured':{'inside':goal} if cross else None}}

class ScoringTests(unittest.TestCase):
    def test_no_goal_is_not_automatically_save(self):
        self.assertEqual(classify(trial(foot=False),trial(goal=True)),'invalid_no_verified_kick')
        t=trial(); t['evaluation']['first_foot_ball']={'time':1}
        self.assertEqual(classify(t,trial(goal=True)),'unresolved_no_goal_no_verified_save')
    def test_contact_on_a_miss_is_not_save(self):
        t=trial(contact=True); t['evaluation']['first_foot_ball']={'time':1}
        self.assertEqual(classify(t,trial()),'miss')
    def test_verified_contact_preventing_goal(self):
        t=trial(contact=True); t['evaluation']['first_foot_ball']={'time':1}
        self.assertEqual(classify(t,trial(goal=True)),'save_with_contact_and_goal_counterfactual')
    def test_goal_has_priority_over_contact(self):
        t=trial(goal=True,contact=True); t['evaluation']['first_foot_ball']={'time':1}
        self.assertEqual(classify(t,trial(goal=True)),'goal')
    def test_interpolation(self):
        trace=[{'observation':{'time_s':0,'keeper_q':0}}, {'observation':{'time_s':1,'keeper_q':0.2}}]
        self.assertAlmostEqual(interpolate_q(trace,.25),.05)
    def test_time_bounds(self):
        self.assertAlmostEqual(min_center_travel_time(.09),.6)
        self.assertAlmostEqual(min_center_travel_time(.39),1.6)

if __name__=='__main__':
    unittest.main()
