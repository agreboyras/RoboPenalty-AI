import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phase8b2.bootstrap
from phase8b2.experiment import identifier,summarize
from phase4b.catalog import CATALOG
import json
from phase8b2.catalog import ShotCatalog

class ConfigurationTests(unittest.TestCase):
    def test_unique_new_ids(self):
        values=[0,.75,-.5,.85,1.,-1.,4.,-4.]
        self.assertEqual(len(set(map(identifier,values))),len(values))
        self.assertFalse(set(map(identifier,values)) & set(CATALOG['long']))
    def test_invalid_search(self):
        for value in [float('nan'),float('inf'),4.001,-4.001]:
            with self.assertRaises(ValueError):identifier(value)
    def test_historical_catalog_unchanged(self):
        self.assertEqual(CATALOG['long'],dict(center=('long_center',0.),left=('long_preset_left',.75),right=('long_preset_right',-.5)))
    def test_frozen_physical_catalog(self):
        catalog=ShotCatalog(Path(__file__).resolve().parent/'catalog_v1.json')
        self.assertEqual(len(catalog.actions),5)
        self.assertFalse({'left','right'} & set(catalog.actions))
        for action,entry in catalog.entries.items():
            r=json.loads(Path(catalog.calibration[action]['source']).read_text(encoding='utf-8'))
            self.assertTrue(r['passed'])
            self.assertGreater(r['evaluation']['foot_peak_force_n'],0)
            self.assertIsNone(r['evaluation']['shooter_fall_time_s'])
            self.assertGreater(1.5-abs(r['evaluation']['goal_crossing_measured']['position_w'][1])-.115,0)
    def test_corner_targets_are_at_goal_plane(self):
        catalog=ShotCatalog(Path(__file__).resolve().parent/'catalog_v1.json')
        for action in ('corner_left_b097','corner_right_m140'):
            r=json.loads(Path(catalog.calibration[action]['source']).read_text(encoding='utf-8'))
            x,y,z=r['evaluation']['goal_crossing_measured']['position_w']
            self.assertEqual(x,5.)
            self.assertTrue(1.10<=abs(y)<=1.30)
            self.assertLess(z,.35)

if __name__=='__main__':unittest.main()
