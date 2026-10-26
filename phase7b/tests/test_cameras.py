from pathlib import Path
import sys
import queue
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'phase6b'))
from phase7b.cameras import specification,ViewCommandBus

class CameraTests(unittest.TestCase):
    def test_execution_preserves_previous_camera(self):
        self.assertEqual(specification('execution'),{'lookat':[1.5,0.,.65],
            'distance':10.5,'azimuth':-60.,'elevation':-22.})
    def test_follow_only_uses_current_ball(self):
        self.assertEqual(specification('follow',(3.,.4,.2))['lookat'],[3.,.4,.65])
    def test_visual_requests_do_not_become_game_commands(self):
        q=queue.Queue(2);bus=ViewCommandBus(camera_requests=q)
        self.assertTrue(bus.submit('/cam overview'))
        self.assertIsNone(bus.drain());self.assertEqual(q.get_nowait(),(0,'overview'))
        bus.submit('Pausar partido');self.assertEqual(bus.drain().intent,'pause')
    def test_unknown_camera_stays_rejected_by_strict_game_parser(self):
        q=queue.Queue(2);bus=ViewCommandBus(camera_requests=q)
        bus.submit('/cam not_a_view');self.assertIsNone(bus.drain().intent);self.assertTrue(q.empty())
    def test_voice_grammar_is_not_extended(self):
        q=queue.Queue(2);bus=ViewCommandBus(camera_requests=q)
        bus.submit('/cam overview','voice');self.assertIsNone(bus.drain().intent);self.assertTrue(q.empty())
    def test_stale_visual_requests_are_rejected(self):
        q=queue.Queue(2);bus=ViewCommandBus(camera_requests=q);bus.rotate()
        self.assertFalse(bus.submit('/cam overview',generation=0));self.assertTrue(q.empty())
    def test_camera_queue_is_bounded(self):
        q=queue.Queue(1);bus=ViewCommandBus(camera_requests=q)
        self.assertTrue(bus.submit('/cam overview'));self.assertFalse(bus.submit('/cam goal'))

if __name__=='__main__':unittest.main(verbosity=2)
