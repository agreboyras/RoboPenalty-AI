"""Owner-thread presentation of the same physical runtime and command service."""
import threading
import time
from session import CommandPresenter
from phase7c.presentation import EnhancedPresenter
from phase7d.visual_scene import StadiumScene,prepare_model
from phase7d.cameras import specification
from phase7d.integrity import model_signature
from presentation import png_write

class MonumentalPresenter(EnhancedPresenter):
    def __init__(self,runtime,config,output,distance,*,lod='medium',camera='behind',camera_requests=None):
        if distance!='long':raise ValueError('7D supports validated long distance only')
        self.lod=lod;self.stage=6;self.decoration=lod!='none';self.view=camera
        self.owner=threading.get_ident();self.camera_requests=camera_requests;self.camera_events=[]
        self.final_captured=False;self.screen_events=[];self.population_wall_s=0.;self.population_calls=0
        self.pause_display_events=[];self.last_pause_display=None
        self.initial_signature=model_signature(runtime.model)
        self.appearance_changes=prepare_model(runtime.model)
        self.visual_scene=StadiumScene(runtime.model,lod)
        CommandPresenter.__init__(self,runtime,config,output,distance)
        self.visual_capacity=None
        if self.handle is not None:
            with self.handle.lock():
                self.visual_capacity=int(self.handle.user_scn.maxgeom)
                self.visual_scene.populate(self.handle.user_scn)
        self.select_camera(camera)

    def select_camera(self,name):
        if threading.get_ident()!=self.owner:raise RuntimeError('Camera selection requires simulation owner')
        self.view=name
        self.camera=specification(name,self.runtime.data.xpos[self.runtime.model.body('ball').id])
        self.camera_events.append(dict(view=name,time_sim_s=float(self.runtime.data.time)))
        self.apply_camera()

    def set_status(self,status):
        if threading.get_ident()!=self.owner:raise RuntimeError('Screen update requires simulation owner')
        before=self.runtime.integration_state(self.runtime.data)
        start=time.perf_counter()
        super().set_status(status)
        self.population_wall_s+=time.perf_counter()-start;self.population_calls+=1
        unchanged=bool(self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data)))
        if not unchanged:raise RuntimeError('Scoreboard rendering changed physics')
        self.screen_events.append(dict(status=dict(status),screen=list(self.visual_scene.screen_state),
                                       time_sim_s=float(self.runtime.data.time),state_unchanged=unchanged))

    def sync(self,kind='transition'):
        paused=bool(self.service and self.service.control.paused)
        key=(paused,tuple(self.visual_scene.screen_state))
        if key!=self.last_pause_display:
            self.pause_display_events.append(dict(paused=paused,screen=list(self.visual_scene.screen_state),
                                                  phase=self.status.get('phase'),time_sim_s=float(self.runtime.data.time)))
            self.last_pause_display=key
        super().sync(kind)

    def render_views(self,prefix):
        start=time.perf_counter();before=self.runtime.integration_state(self.runtime.data)
        with self.mj.Renderer(self.runtime.model,height=640,width=960) as renderer:
            for name in ('behind','execution','overview','goal'):
                spec=specification(name);cam=self.mj.MjvCamera();self.mj.mjv_defaultCamera(cam)
                cam.lookat[:]=spec['lookat'];cam.distance=spec['distance']
                cam.azimuth=spec['azimuth'];cam.elevation=spec['elevation']
                renderer.update_scene(self.runtime.data,camera=cam)
                self.visual_scene.populate(renderer.scene,replace=False)
                png_write(self.output/f'{prefix}_{name}.png',renderer.render())
        if not self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data)):
            raise RuntimeError('Capture changed physical state')
        self.capture_wall_s+=time.perf_counter()-start

    def summary(self):
        unchanged=self.initial_signature==model_signature(self.runtime.model)
        if not unchanged:raise RuntimeError('Physical model changed in 7D')
        return {**CommandPresenter.summary(self),'episodes':self.episodes,'stadium':{
            'physical_model_unchanged':unchanged,'visual_geom_count':len(self.visual_scene.primitives),
            'visual_capacity':self.visual_capacity,'camera_events':self.camera_events,'view':self.view,
            'decoration':self.decoration,'model_signature':self.initial_signature},'phase7d':{
            'lod':self.lod,'screen_state':self.visual_scene.screen_state,'screen_updates':self.visual_scene.screen_updates,
            'screen_events':self.screen_events,'pause_display_events':self.pause_display_events,
            'status_update_wall_s_including_optional_capture':self.population_wall_s,'status_update_calls':self.population_calls,
            'appearance_changes':self.appearance_changes}}
