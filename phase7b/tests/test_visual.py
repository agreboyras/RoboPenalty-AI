from pathlib import Path
import sys
import unittest
import mujoco
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from phase7b.visual_scene import VisualScene,turf,apply_appearance,stadium
from phase7b.integrity import model_signature
from phase7b import layout

class VisualTests(unittest.TestCase):
    def setUp(self):
        self.model=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="plane" size="0 0 .01"/></worldbody></mujoco>')
    def test_turf_covers_approved_rectangle(self):
        strips=turf()
        self.assertEqual(min(p.position[0]-p.size[0] for p in strips),-15)
        self.assertEqual(max(p.position[0]+p.size[0] for p in strips),5)
        self.assertTrue(all(p.size[1]==12 for p in strips))
    def test_populate_is_idempotent_and_not_physical(self):
        before=model_signature(self.model)
        s=mujoco.MjvScene(self.model,100)
        visual=VisualScene(2);visual.populate(s);visual.populate(s)
        self.assertEqual(s.ngeom,10)
        self.assertEqual(before,model_signature(self.model))
        self.assertTrue(all(g.objid==-1 for g in s.geoms[:s.ngeom]))
    def test_capacity_checked_before_writing(self):
        s=mujoco.MjvScene(self.model,2)
        with self.assertRaises(RuntimeError):VisualScene(2).populate(s)
        self.assertEqual(s.ngeom,0)
    def test_append_preserves_existing_geometry(self):
        s=mujoco.MjvScene(self.model,100);s.ngeom=1
        s.geoms[0].pos[:]=[7,8,9]
        VisualScene(2).populate(s,replace=False)
        self.assertEqual(s.ngeom,11)
        np.testing.assert_array_equal(s.geoms[0].pos,[7,8,9])
    def test_signature_detects_physical_change(self):
        before=model_signature(self.model)
        self.model.geom_friction[0,0]=.123
        self.assertNotEqual(before,model_signature(self.model))
    def test_penalty_arc_is_only_outside_area(self):
        points=layout.penalty_arc()
        self.assertTrue(all(x<=-4+1e-12 for x,y in points))
        for x,y in points:self.assertAlmostEqual((x+1)**2+y*y,3.5**2)
        self.assertAlmostEqual(points[0][0],-4)
        self.assertAlmostEqual(points[-1][0],-4)
    def test_center_arc_is_only_inside_half(self):
        self.assertTrue(all(x>=-15-1e-12 for x,y in layout.center_semicircle()))
    def test_point_matches_validated_ball_xy(self):
        point=next(p for p in VisualScene(3).primitives if p.name=='penalty_spot')
        self.assertEqual(point.position[:2],(-1.,0.))
    def test_one_goal_line_and_correct_box_fronts(self):
        segments={name:(a,b) for name,a,b in layout.marking_segments()}
        self.assertEqual(segments['goal_line'],((5,-12),(5,12)))
        self.assertEqual(segments['penalty_front'],((-4.,-7.),(-4.,7.)))
        self.assertEqual(segments['small_front'],((2.,-3.5),(2.,3.5)))
    def test_markings_initialize_valid_rotations(self):
        scene=mujoco.MjvScene(self.model,200)
        VisualScene(3).populate(scene)
        for geom in scene.geoms[:scene.ngeom]:
            # MjvGeom matrices are float32, unlike physical state arrays.
            np.testing.assert_allclose(geom.mat.T@geom.mat,np.eye(3),
                                       rtol=0,atol=4*np.finfo(geom.mat.dtype).eps)
    def test_appearance_preserves_backstop_and_goal_physics(self):
        m=mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
            <geom name="floor" type="plane" size="0 0 .01"/>
            <geom name="pitch_shot_spot" type="sphere" size=".1" contype="0" conaffinity="0"/>
            <geom name="goal_left_post" type="sphere" size=".1" contype="0" conaffinity="0"/>
            <body pos="5.5 0 1"><freejoint/><geom name="box_geom" type="box" size=".3 5 1" mass="1000"/></body>
            </worldbody></mujoco>''')
        before=model_signature(m)
        apply_appearance(m,4)
        self.assertEqual(before,model_signature(m))
        self.assertEqual(m.geom_rgba[m.geom('box_geom').id,3],0)
        self.assertEqual(m.geom_contype[m.geom('box_geom').id],1)
        self.assertEqual(m.geom_rgba[m.geom('goal_left_post').id,3],1)
    def test_decoration_is_outside_playing_rectangle(self):
        for p in stadium():
            if p.end is not None:
                self.assertTrue(all(x<-15 or x>5 or abs(y)>12 for x,y,z in (p.position,p.end)))
            else:
                x,y,z=p.position;hx,hy,hz=p.size
                self.assertTrue(x+hx<=-15 or x-hx>=5 or y+hy<=-12 or y-hy>=12,p.name)
    def test_decoration_can_be_removed_without_losing_marks(self):
        self.assertEqual(VisualScene(6,False).primitives,VisualScene(5).primitives)
        self.assertGreater(len(VisualScene(6).primitives),len(VisualScene(6,False).primitives))
    def test_stadium_is_bounded_and_native_initialization_works(self):
        visual=VisualScene(6);self.assertLess(len(visual.primitives),400)
        scene=mujoco.MjvScene(self.model,400);before=model_signature(self.model)
        visual.populate(scene)
        self.assertEqual(before,model_signature(self.model))
        self.assertTrue(np.isfinite([g.pos for g in scene.geoms[:scene.ngeom]]).all())

if __name__=='__main__':unittest.main(verbosity=2)
