"""Derived presenter; stage zero is the unmodified 7B appearance."""
from phase7b.presentation import StadiumPresenter
from session import CommandPresenter
from presentation import png_write
from phase7c.integrity import model_signature
from phase7c.visual_scene import EnhancedScene,prepare_model
from phase7c.cameras import specification
import time
import threading

class EnhancedPresenter(StadiumPresenter):
    def __init__(self,runtime,config,output,distance,*,enhancement_stage=0,lod='medium',
                 camera='behind',camera_requests=None):
        if distance!='long':raise ValueError('Only validated long distance is supported')
        self.enhancement_stage=enhancement_stage;self.lod=lod
        self.stage=6;self.decoration=lod!='none';self.view=camera
        self.owner=threading.get_ident();self.camera_requests=camera_requests;self.camera_events=[]
        self.final_captured=False
        self.initial_signature=model_signature(runtime.model)
        self.visual_scene=EnhancedScene(runtime.model,enhancement_stage,lod)
        self.appearance_changes=prepare_model(runtime.model,enhancement_stage)
        CommandPresenter.__init__(self,runtime,config,output,distance)
        self.visual_capacity=None
        if self.handle is not None:
            with self.handle.lock():
                self.visual_capacity=int(self.handle.user_scn.maxgeom)
                self.visual_scene.populate(self.handle.user_scn)
        self.select_camera(camera)

    def select_camera(self,name):
        if threading.get_ident()!=self.owner:raise RuntimeError('Owner-thread camera selection required')
        self.view=name
        self.camera=specification(name,self.runtime.data.xpos[self.runtime.model.body('ball').id])
        self.camera_events.append({'view':name,'time_sim_s':float(self.runtime.data.time)})
        self.apply_camera()

    def summary(self):
        result=CommandPresenter.summary(self)
        unchanged=self.initial_signature==model_signature(self.runtime.model)
        if not unchanged:raise RuntimeError('Physical model changed in phase7c')
        return {**result,'episodes':self.episodes,'stadium':{
            'stage':self.enhancement_stage,'decoration':self.decoration,'view':self.view,
            'physical_model_unchanged':unchanged,'visual_geom_count':len(self.visual_scene.primitives),
            'visual_capacity':self.visual_capacity,'appearance_changes':self.appearance_changes,
            'camera_events':self.camera_events,'model_signature':self.initial_signature},
            'phase7c':{'stage':self.enhancement_stage,'lod':self.lod,
                      'screen_state':self.visual_scene.screen_state,
                      'screen_updates':self.visual_scene.screen_updates}}

    def set_status(self,status):
        CommandPresenter.set_status(self,status)
        if self.visual_scene.update_status(status) and self.handle is not None:
            with self.handle.lock():self.visual_scene.populate(self.handle.user_scn)
        if status.get('phase')=='FINISHED' and self.config.capture_frame and not self.final_captured:
            self.render_views('final');self.final_captured=True

    def capture(self):
        if not self.config.capture_frame or self.captured:return
        self.render_views('initial');self.captured=True

    def render_views(self,prefix):
        start=time.perf_counter();before=self.runtime.integration_state(self.runtime.data)
        m=self.runtime.model
        with self.mj.Renderer(m,height=640,width=960) as renderer:
            for name in ('behind','execution','overview','goal'):
                spec=specification(name)
                cam=self.mj.MjvCamera();self.mj.mjv_defaultCamera(cam)
                cam.lookat[:]=spec['lookat'];cam.distance=spec['distance']
                cam.azimuth=spec['azimuth'];cam.elevation=spec['elevation']
                renderer.update_scene(self.runtime.data,camera=cam)
                self.visual_scene.populate(renderer.scene,replace=False)
                png_write(self.output/f'{prefix}_{name}.png',renderer.render())
        if not self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data)):
            raise RuntimeError('Rendering changed integration state')
        self.capture_wall_s+=time.perf_counter()-start
