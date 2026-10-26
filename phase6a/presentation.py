"""Native passive-viewer presentation; no physics steps, agent decisions or scoring."""
from dataclasses import dataclass,asdict
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import zlib

class ViewerClosed(RuntimeError): pass
class ViewerPhysicsChange(RuntimeError): pass

@dataclass(frozen=True)
class PresentationConfig:
    enabled:bool=False
    fps:float=30.
    realtime:bool=True
    before_shot_s:float=1.
    after_result_s:float=1.5
    before_reset_s:float=.5
    end_s:float=3.
    capture_frame:bool=False

    def __post_init__(self):
        values=(self.fps,self.before_shot_s,self.after_result_s,self.before_reset_s,self.end_s)
        if not all(math.isfinite(v) for v in values) or self.fps<=0 or min(values[1:])<0:
            raise ValueError('Finite positive FPS and nonnegative presentation pauses required')

def png_write(path,pixels):
    """Encode a simulation RGB frame with the standard library; no new dependency."""
    h,w,_=pixels.shape
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+row.tobytes() for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

class Presenter:
    def __init__(self,runtime,config,output,distance):
        self.runtime,self.config,self.output=runtime,config,Path(output)
        self.mj=runtime.engine.mujoco
        self.handle=None;self.status={};self.goal_q=0.;self.frames=0
        self.open_wall_s=self.close_wall_s=self.capture_wall_s=0.
        self.pacing_sleep_s=0.;self.sync_times={'physics':0.,'pause':0.,'transition':0.}
        self.pauses=[];self.episodes=[];self.events=[]
        self.closed=False;self.captured=False;self.guard_checks=0
        self.camera={'lookat':[1.5 if distance=='long' else 2.5,0.,.65],
                     'distance':10.5 if distance=='long' else 9.,'azimuth':-60.,'elevation':-22.}
        if config.enabled:
            import mujoco.viewer
            start=time.perf_counter()
            self.handle=mujoco.viewer.launch_passive(runtime.model,runtime.data,show_left_ui=False,show_right_ui=False)
            self.open_wall_s=time.perf_counter()-start
            with self.handle.lock():
                self.handle.cam.lookat[:]=self.camera['lookat']
                self.handle.cam.distance=self.camera['distance']
                self.handle.cam.azimuth=self.camera['azimuth'];self.handle.cam.elevation=self.camera['elevation']
            self.launch_model_id=id(runtime.model);self.launch_data_id=id(runtime.data)

    def require_open(self):
        if self.handle is not None and not self.handle.is_running():raise ViewerClosed('Viewer closed; unfinished penalty is not scored')

    def option_signature(self):
        opt=self.runtime.model.opt
        values={name:(getattr(opt,name).tolist() if hasattr(getattr(opt,name),'tolist') else getattr(opt,name))
                for name in dir(opt) if not name.startswith('_') and not callable(getattr(opt,name))}
        return json.dumps(values,sort_keys=True)

    def overlay(self):
        s=self.status;d=self.runtime.data
        left='RoboPenalty\nPenal\nGoles / Atajadas / Errados\nEstado\nPreset\nUltimo resultado\nObjetivo arquero q [m]\nPosicion arquero q [m]\nTiempo simulado [s]'
        right=f'AI\n{s.get("penalty",0)}/{s.get("total",0)}\n{s.get("goals",0)} / {s.get("saves",0)} / {s.get("misses",0)}\n{s.get("phase","READY")}\n{s.get("action") or "-"}\n{s.get("last_result") or "-"}\n{self.goal_q:+.3f}\n{float(d.qpos[self.runtime.rail.qpos]):+.3f}\n{float(d.time):.2f}'
        self.handle.set_texts((self.mj.mjtFontScale.mjFONTSCALE_100,self.mj.mjtGridPos.mjGRID_TOPLEFT,left,right))

    def sync(self,kind='transition'):
        if self.handle is None:return
        self.require_open();self.overlay()
        before=self.runtime.integration_state(self.runtime.data)
        options=self.option_signature()
        start=time.perf_counter();self.handle.sync(state_only=True)
        self.sync_times[kind]+=time.perf_counter()-start
        self.frames+=1;self.guard_checks+=1
        # GUI controls/perturbations are never allowed to become an input to the
        # game. Detect a change before the next physics step and abort, not undo.
        if not self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data)) or options!=self.option_signature():
            raise ViewerPhysicsChange('Viewer attempted to change authoritative physics; episode aborted')

    def set_status(self,status):
        self.status=dict(status)
        self.events.append({**status,'time_sim_s':float(self.runtime.data.time),'viewer_running':self.handle.is_running() if self.handle else False})

    def pause(self,kind,seconds):
        if self.handle is None:return
        before=self.runtime.integration_state(self.runtime.data)
        start=time.perf_counter();sleep_s=0.;sync_before=self.sync_times['pause']
        self.sync('pause')
        while time.perf_counter()-start<seconds:
            remaining=seconds-(time.perf_counter()-start)
            if remaining>0:
                t=time.perf_counter();time.sleep(min(1/self.config.fps,remaining));sleep_s+=time.perf_counter()-t
            self.sync('pause')
        after=self.runtime.integration_state(self.runtime.data)
        unchanged=bool(self.runtime.engine.np.array_equal(before,after))
        if not unchanged:raise ViewerPhysicsChange('Presentation pause changed the integration state')
        self.pauses.append({'kind':kind,'penalty':self.status.get('penalty'),'requested_s':seconds,
            'wall_s':time.perf_counter()-start,'sleep_s':sleep_s,
            'sync_wall_s':self.sync_times['pause']-sync_before,'physics_unchanged':unchanged,
            'time_sim_s':float(self.runtime.data.time)})

    def begin_episode(self):
        self.episode_start=time.perf_counter();self.sim_start=float(self.runtime.data.time)
        self.next_sync=self.sim_start;self.goal_q=0.
        self.sync('transition')

    def after_step(self):
        if self.handle is None:return
        now=float(self.runtime.data.time)
        if now+1e-10<self.next_sync:return
        self.sync('physics');self.next_sync=now+1/self.config.fps
        if self.config.realtime:
            wait=self.episode_start+now-self.sim_start-time.perf_counter()
            if wait>0:
                start=time.perf_counter();time.sleep(wait);self.pacing_sleep_s+=time.perf_counter()-start

    def capture(self):
        if self.handle is None or not self.config.capture_frame or self.captured:return
        start=time.perf_counter();before=self.runtime.integration_state(self.runtime.data)
        # A read-only rendering of the SAME world/camera, not another simulation.
        m=self.runtime.model
        width=min(960,int(m.vis.global_.offwidth));height=min(720,int(m.vis.global_.offheight))
        with self.mj.Renderer(m,height=height,width=width) as renderer:
            with self.handle.lock():renderer.update_scene(self.runtime.data,camera=self.handle.cam,scene_option=self.handle.opt)
            pixels=renderer.render();png_write(self.output/'camera_frame.png',pixels)
            previews=[]
            for azimuth in (-60.,-40.,60.,115.):
                camera=self.mj.MjvCamera();self.mj.mjv_defaultCamera(camera)
                camera.lookat[:]=self.camera['lookat'];camera.distance=self.camera['distance']
                camera.azimuth=azimuth;camera.elevation=self.camera['elevation']
                renderer.update_scene(self.runtime.data,camera=camera,scene_option=self.handle.opt)
                path=self.output/f'camera_azimuth_{int(azimuth)}.png'
                png_write(path,renderer.render())
                previews.append({'azimuth':azimuth,'path':str(path),'eye_position_w':renderer.scene.camera[0].pos.tolist()})
            (self.output/'camera_preview_metadata.json').write_text(json.dumps(previews,indent=2),encoding='utf-8')
        assert self.runtime.engine.np.array_equal(before,self.runtime.integration_state(self.runtime.data))
        self.capture_wall_s+=time.perf_counter()-start;self.captured=True

    def close(self):
        if self.handle is None:self.closed=True;return
        start=time.perf_counter();self.handle.close()
        deadline=start+3.
        while self.handle.is_running() and time.perf_counter()<deadline:time.sleep(.01)
        self.closed=not self.handle.is_running();self.close_wall_s=time.perf_counter()-start
        if not self.closed:raise RuntimeError('Native viewer did not close')

    def summary(self):
        return {'config':asdict(self.config),'camera':self.camera,'viewer_open_wall_s':self.open_wall_s,
            'viewer_close_wall_s':self.close_wall_s,'viewer_closed':self.closed,'sync_count':self.frames,
            'sync_call_wall_s_by_kind':self.sync_times,'physics_guard_checks':self.guard_checks,
            'pacing_sleep_wall_s':self.pacing_sleep_s,'capture_wall_s':self.capture_wall_s,
            'presentation_pause_wall_s':sum(p['wall_s'] for p in self.pauses),
            'presentation_sleep_wall_s':sum(p['sleep_s'] for p in self.pauses),
            'pause_records':self.pauses,'events':self.events,
            'same_world_passed_to_viewer':self.handle is None or (self.launch_model_id==id(self.runtime.model) and self.launch_data_id==id(self.runtime.data)),
            'note':'sync timings are CPU wall time of the sync call, not total native render/GPU time; pause wall includes its sync time.'}
