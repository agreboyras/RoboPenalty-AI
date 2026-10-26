"""Small extension of the 6B presenter; stage 1 changes no model data."""
from session import CommandPresenter
from phase7b.integrity import model_signature
from phase7b.visual_scene import VisualScene, apply_appearance
from presentation import png_write
import time
import queue
import threading
from phase7b.cameras import specification

class StadiumPresenter(CommandPresenter):
    def __init__(self, runtime, config, output, distance, *, stage=1,
                 decoration=True, camera='execution', camera_requests=None):
        if distance != 'long':
            raise ValueError('The adapted half pitch supports long only; use the original launcher for original distance')
        self.stage, self.decoration, self.view = stage, decoration, camera
        if stage<5 and camera!='execution':raise ValueError('Camera presets require stage >= 5')
        self.owner=threading.get_ident()
        self.camera_requests=camera_requests
        self.camera_events=[]
        self.initial_signature = model_signature(runtime.model)
        self.visual_scene=VisualScene(stage, decoration)
        self.appearance_changes=apply_appearance(runtime.model,stage)
        if stage>=5:
            # Rendering distance in extent units: 125 * 0.8 = 100 m.
            runtime.model.vis.map.zfar=125.
        super().__init__(runtime, config, output, distance)
        self.visual_capacity=None
        if self.handle is not None:
            with self.handle.lock():
                self.visual_capacity=int(self.handle.user_scn.maxgeom)
                self.visual_scene.populate(self.handle.user_scn)
        if stage>=5:self.select_camera(camera)

    def select_camera(self,name):
        if threading.get_ident()!=self.owner:raise RuntimeError('Camera must be selected by owner thread')
        if self.stage<5:raise ValueError('Camera presets require stage >= 5')
        ball=self.runtime.data.xpos[self.runtime.model.body('ball').id]
        self.view=name;self.camera=specification(name,ball)
        self.camera_events.append({'view':name,'time_sim_s':float(self.runtime.data.time)})
        self.apply_camera()

    def apply_camera(self):
        if self.handle is None:return
        with self.handle.lock():
            self.handle.cam.lookat[:]=self.camera['lookat']
            for name in ('distance','azimuth','elevation'):setattr(self.handle.cam,name,self.camera[name])

    def sync(self,kind='transition'):
        if self.camera_requests is not None:
            while True:
                try:epoch,view=self.camera_requests.get_nowait()
                except queue.Empty:break
                if self.service and epoch!=self.service.control.bus.epoch():continue
                if self.stage<5:
                    print('[camara] Rechazada: requiere etapa >= 5',file=self.runtime.console,flush=True)
                    continue
                self.select_camera(view)
                print('[camara] '+view,file=self.runtime.console,flush=True)
        if self.stage>=5 and self.view=='follow':
            self.camera=specification('follow',self.runtime.data.xpos[self.runtime.model.body('ball').id])
            self.apply_camera()
        super().sync(kind)

    def summary(self):
        result = super().summary()
        unchanged = self.initial_signature == model_signature(self.runtime.model)
        if not unchanged: raise RuntimeError('Physical model changed in visual adapter')
        return {**result, 'episodes':self.episodes,'stadium': {'stage':self.stage,'decoration':self.decoration,
                'view':self.view,'physical_model_unchanged':unchanged,
                'visual_geom_count':len(self.visual_scene.primitives),
                'visual_capacity':self.visual_capacity,'appearance_changes':self.appearance_changes,
                'camera_events':self.camera_events,'render_far_m':float(self.runtime.model.vis.map.zfar*self.runtime.model.stat.extent),
                'model_signature':self.initial_signature}}

    def capture(self):
        if not self.config.capture_frame or self.captured:return
        start=time.perf_counter()
        before=self.runtime.integration_state(self.runtime.data)
        model=self.runtime.model
        width=min(960,int(model.vis.global_.offwidth));height=min(720,int(model.vis.global_.offheight))
        with self.mj.Renderer(model,height=height,width=width) as renderer:
            for name in (('execution','overview','goal') if self.stage>=5 else ('execution',)):
                spec=specification(name)
                camera=self.mj.MjvCamera();self.mj.mjv_defaultCamera(camera)
                camera.lookat[:]=spec['lookat'];camera.distance=spec['distance']
                camera.azimuth=spec['azimuth'];camera.elevation=spec['elevation']
                renderer.update_scene(self.runtime.data,camera=camera)
                self.visual_scene.populate(renderer.scene,replace=False)
                png_write(self.output/f'camera_{name}.png',renderer.render())
        if not self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data)):
            raise RuntimeError('Offscreen rendering changed physics')
        self.capture_wall_s+=time.perf_counter()-start;self.captured=True
