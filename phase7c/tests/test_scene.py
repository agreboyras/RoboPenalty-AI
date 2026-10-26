from pathlib import Path
import sys
import unittest
import numpy as np
import mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'phase6b'))
from phase7c.visual_scene import grass_pixels
from phase7c.cameras import specification
from phase7c.integrity import model_signature
from phase7c.environment import crowd,terraces,goal_net
from phase7c.scoreboard import lettering,screen_frame,score_lines,rectangles,FONT
from phase7c.cameras import CameraBus
import queue

class VisualTests(unittest.TestCase):
    def test_texture_is_deterministic_rgb_and_not_flat(self):
        a=grass_pixels(300,300)
        self.assertEqual(a.shape,(300,300,3));self.assertEqual(a.dtype,np.uint8)
        np.testing.assert_array_equal(a,grass_pixels(300,300))
        self.assertGreater(a.std(),2)
    def test_visual_rng_does_not_change_agent_rng(self):
        np.random.seed(123);before=np.random.get_state()
        grass_pixels(30,30);after=np.random.get_state()
        self.assertEqual(before[0],after[0]);np.testing.assert_array_equal(before[1],after[1])
        self.assertEqual(before[2:],after[2:])
    def test_camera_is_behind_and_raised(self):
        c=specification('behind')
        self.assertTrue(0<c['azimuth']<30);self.assertLess(c['elevation'],0)
        self.assertGreater(c['distance'],6)
    def test_physical_changes_remain_detectable(self):
        m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="sphere" size=".1"/></worldbody></mujoco>')
        old=model_signature(m);m.geom_friction[0,0]=.333
        self.assertNotEqual(old,model_signature(m))
    def test_crowd_is_bounded_and_lod_reduces_cost(self):
        self.assertLess(len(crowd('medium')),300)
        self.assertLess(len(crowd('low')),len(crowd('medium')))
        self.assertEqual(crowd('medium'),crowd('medium'))
    def test_crowd_and_terraces_are_outside_pitch(self):
        for p in terraces('medium'):
            if p.end is not None:
                self.assertTrue(all(x>5 or x<-15 or abs(y)>12 for x,y,z in (p.position,p.end)),p.name)
            else:
                x,y,z=p.position;hx,hy,hz=p.size
                if p.kind=='sphere':hy=hx
                self.assertTrue(x-hx>=5 or x+hx<=-15 or abs(y)-hy>=12,p.name)
    def test_net_preserves_nominal_goal_bounds_and_depth(self):
        net=goal_net('medium')
        self.assertLess(len(net),100)
        for p in net:
            for x,y,z in (p.position,p.end):
                self.assertTrue(5<=x<=6.1 and abs(y)<=1.5 and 0<=z<=1.8)
    def test_identity_and_score_are_world_geometries_not_overlay_only(self):
        self.assertGreater(len(lettering('ROBOPENALTY AI',5.95,.1,'title')),40)
        self.assertNotEqual(score_lines({'goals':0,'saves':0}),score_lines({'goals':3,'saves':2}))
        self.assertTrue(all(p.position[0]>5 for p in screen_frame()))
    def test_camera_queue_does_not_change_voice_parser(self):
        q=queue.Queue(2);bus=CameraBus(camera_requests=q)
        bus.submit('/cam behind');self.assertEqual(q.get_nowait(),(0,'behind'));self.assertIsNone(bus.drain())
        bus.submit('/cam behind','voice');self.assertIsNone(bus.drain().intent)
        bus.submit('Pausar partido');self.assertEqual(bus.drain().intent,'pause')
    def test_actual_model_and_state_are_invariant_at_every_visual_stage(self):
        from phase7c.preview import prepared_world
        from phase7c.visual_scene import EnhancedScene,prepare_model
        m,d,_=prepared_world();before=model_signature(m)
        state=d.qpos.tobytes()+d.qvel.tobytes()
        for stage in (0,1,2,3):
            scene=EnhancedScene(m,stage,'medium');prepare_model(m,stage)
            target=mujoco.MjvScene(m,1500);scene.populate(target)
            scene.update_status({'goals':3,'saves':2,'penalty':5,'total':5});scene.populate(target)
            self.assertEqual(before,model_signature(m));self.assertEqual(state,d.qpos.tobytes()+d.qvel.tobytes())
            self.assertLess(target.ngeom,1100);self.assertEqual(m.nlight,2)
            if stage==3:
                updates=scene.screen_updates
                self.assertFalse(scene.update_status({'goals':3,'saves':2,'penalty':5,'total':5}))
                self.assertEqual(scene.screen_updates,updates)
    def test_visual_texture_exclusion_does_not_exclude_contact_parameters(self):
        m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="sphere" size=".1"/></worldbody></mujoco>')
        before=model_signature(m)
        for field in ('geom_size','geom_solref','geom_contype'):
            value=getattr(m,field).copy();getattr(m,field).flat[0]+=1
            self.assertNotEqual(before,model_signature(m));getattr(m,field)[:]=value
    def test_optimized_letters_preserve_every_pixel_without_overlaps(self):
        for glyph in FONT.values():
            image=np.zeros((7,5),dtype=int)
            for row,col,height,width in rectangles(glyph):image[row:row+height,col:col+width]+=1
            expected=np.array([[int(v) for v in row] for row in glyph])
            np.testing.assert_array_equal(image,expected)

if __name__=='__main__':unittest.main(verbosity=2)
