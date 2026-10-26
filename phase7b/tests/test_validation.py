from pathlib import Path
import copy
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from phase7b.validate import learning_payload

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.feedback={'record':{'wall_s':1.,'physics_call_wall_s':.9,'outcome':'goal',
                       'simulated_s':14.},'update':{'count':1},'statistics_after':{'goals':1}}
    def test_only_wall_clock_measurements_are_excluded(self):
        other=copy.deepcopy(self.feedback)
        other['record']['wall_s']=70.;other['record']['physics_call_wall_s']=60.
        self.assertEqual(learning_payload(other),learning_payload(self.feedback))
    def test_result_and_learning_changes_are_not_hidden(self):
        for container,key,value in [('record','outcome','save'),('record','simulated_s',13.),
                                    ('update','count',2),('statistics_after','goals',0)]:
            other=copy.deepcopy(self.feedback);other[container][key]=value
            self.assertNotEqual(learning_payload(other),learning_payload(self.feedback))

if __name__=='__main__':unittest.main(verbosity=2)
