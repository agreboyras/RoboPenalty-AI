from bootstrap import *
import json
import unittest
from types import SimpleNamespace
import numpy as np
from phase8c.catalog import Catalog
from phase8c.runtime import components
from phase9a.bus import InputBus
from phase9a.control import Control
from phase9a.selection import SelectionRouter

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=Catalog(PROJECT/'phase8c/catalog_v1.json');_,cls.Auto=components(cls.catalog)
        import sys
        cls.Observation=sys.modules['phase8b2_owned_selector'].InitialObservation
    def setup_router(self,mode='directed'):
        bus=InputBus();c=Control(bus,mode,emit=lambda *a,**k:None);c.phase='PREPARING';c.active=True;c.penalty=1
        runtime=SimpleNamespace(data=SimpleNamespace(time=0.),engine=SimpleNamespace(np=np),integration_state=lambda d:np.zeros(4))
        service=SimpleNamespace(control=c,runtime=runtime,voice_on_wait=False,checkpoint=lambda:None)
        service.idle=lambda:(bus.submit('Patea al centro'),c.pump())
        router=SelectionRouter(self.Auto(),service)
        observation=self.Observation('long','agent',0.,0.,0.,.2,.115,(-1,0,.115),(-2,0,.793),self.catalog.actions)
        return router,service,observation
    def test_manual_feedback_never_changes_automatic_state(self):
        router,s,o=self.setup_router();before=router.snapshot()
        phrases=['Patea al centro','Patea a la izquierda','Patea a la derecha','Patea a la derecha abierta','Patea a la esquina derecha']
        for n,text in enumerate(phrases):
            s.idle=lambda t=text:(s.control.bus.submit(t),s.control.pump())
            router.choose(o,self.catalog.calibration,str(n));self.assertEqual(router.snapshot(),before)
            router.observe(str(n),'goal');self.assertEqual(router.snapshot(),before)
        self.assertEqual(len(router.manual_history),5);self.assertTrue(all(w['full_physics_unchanged'] for w in router.waits))
    def test_auto_is_exact_original_selector(self):
        router,s,o=self.setup_router('auto');original=self.Auto()
        for n in range(5):
            a=router.choose(o,self.catalog.calibration,str(n));b=original.choose(o,self.catalog.calibration,str(n))
            self.assertEqual(a,b);router.observe(str(n),'goal');original.observe(str(n),'goal')
            self.assertEqual(router.snapshot(),original.snapshot())
    def test_switch_at_wait_routes_to_auto_without_manual_label(self):
        router,s,o=self.setup_router()
        s.idle=lambda:(s.control.bus.submit('Modo automatico'),s.control.pump())
        decision=router.choose(o,self.catalog.calibration,'p1')
        self.assertEqual(decision['strategy'],'utility');self.assertEqual(router.manual_history,[])
        router.observe('p1','save');self.assertEqual(len(router.snapshot()['history']),1)
    def test_double_feedback_rejected(self):
        r,s,o=self.setup_router();r.choose(o,self.catalog.calibration,'p1');r.observe('p1','goal')
        with self.assertRaises(RuntimeError):r.observe('p1','goal')

if __name__=='__main__':unittest.main()
