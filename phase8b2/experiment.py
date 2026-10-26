"""Bias-only experiments around the existing physical runner. No ball control."""
import contextlib
import hashlib
import io
import json
import math
from argparse import Namespace
from pathlib import Path
import time
from phase5.runtime import SimulationRuntime
from phase7c.integrity import model_signature


def identifier(bias):
    if not math.isfinite(bias) or abs(bias)>4:
        raise ValueError('Experimental bias must be finite and within the explicit search bound ±4 (not a trained range)')
    return 'bias_' + ('p' if bias>=0 else 'm') + f'{abs(bias):.4f}'.replace('.', '_')


class BallRecorder:
    """Read-only samples after the real mj_step, including positive foot forces."""
    def __init__(self, base, runtime):
        self.base, self.runtime = base, runtime
        self.rows=[];self.impacts=[]
    def __getattr__(self,key): return getattr(self.base,key)
    def mj_step(self,m,d,*a,**kw):
        value=self.base.mj_step(m,d,*a,**kw)
        r=self.runtime
        ball=m.body('ball').id; j=int(m.body_jntadr[ball])
        q=int(m.jnt_qposadr[j]); v=int(m.jnt_dofadr[j]); g=m.geom('ball_geom').id
        force=0.
        for n,c in enumerate(d.contact[:d.ncon]):
            other=int(c.geom2) if int(c.geom1)==g else int(c.geom1) if int(c.geom2)==g else None
            if other in r.shooter.foot_geoms:
                f=r.engine.np.zeros(6);self.base.mj_contactForce(m,d,n,f);force=max(force,float(f[0]))
                if f[0]>0:
                    self.impacts.append(dict(time_s=float(d.time),contact_position_w=c.pos.tolist(),
                        foot_geom=m.geom(other).name,normal_force_n=float(f[0]),
                        ball_position_after_step_w=d.qpos[q:q+3].tolist(),ball_velocity_after_step_w=d.qvel[v:v+3].tolist()))
        self.rows.append([float(d.time),*d.qpos[q:q+3].tolist(),*d.qvel[v:v+3].tolist(),force])
        return value


class BiasRuntime(SimulationRuntime):
    def __init__(self):
        super().__init__()
        self.physical_signature=model_signature(self.model)
        self.recorder=BallRecorder(self.engine.mujoco,self)
        self.engine.mujoco=self.recorder

    def trial(self,bias,output,mode='probe',duration=14.):
        output=Path(output)
        name=identifier(bias); e=self.engine
        e.SCENARIOS={name:dict(translate_x=-2.,target_bias=float(bias))}
        e.initialize=self.original_initialize
        self.recorder.rows=[];self.recorder.impacts=[]
        start=time.perf_counter()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                status=e.run(Namespace(output=str(output),mode=mode,scenario=name,duration=duration))
            result=json.loads(output.read_text(encoding='utf-8'))
            result['phase8b2']={'bias':bias,'wall_s':time.perf_counter()-start,
                'return_code':status,'trajectory_columns':['t','x','y','z','vx','vy','vz','foot_normal_force_n'],
                'trajectory':self.recorder.rows,'positive_foot_contacts':self.recorder.impacts,
                'final_state_sha256':hashlib.sha256(self.integration_state(self.data).tobytes()).hexdigest()}
            output.write_text(json.dumps(result,indent=2),encoding='utf-8')
            return result
        finally:
            # Probe relocation belongs solely to initial conditions of that episode.
            self.model.body_pos[:]=self.initial_model_body_pos
            if model_signature(self.model)!=self.physical_signature:
                raise AssertionError('Compiled physics changed after restoring probe-only keeper origin')


def summarize(r,path):
    e=r['evaluation']; rows=r['phase8b2']['trajectory']
    impacts=[i for i,row in enumerate(rows) if row[7]>0]
    # First free sample after the LAST positive foot contact; no arbitrary time offset.
    release=rows[impacts[-1]+1] if impacts and impacts[-1]+1<len(rows) else None
    goal=e['goal_crossing_measured']; approach=e['approach_crossing_measured']
    y=goal['position_w'][1] if goal else None
    return dict(source=str(path),bias=r['phase8b2']['bias'],passed=r['passed'],failures=r['failures'],
        contact=e['first_foot_ball'],foot_peak_n=e['foot_peak_force_n'],release=release,
        release_angle_deg=math.degrees(math.atan2(release[5],release[4])) if release else None,
        plane4=approach,plane5=goal,post_center_gap_m=1.5-abs(y) if y is not None else None,
        sphere_post_margin_m=1.5-abs(y)-.115 if y is not None else None,
        outcome='invalid' if not r['passed'] else 'goal' if e['goal_detected'] else 'miss' if goal else 'short_or_stopped',
        low_corner=bool(goal and 1.10<=abs(y)<=1.30 and .10<=goal['position_w'][2]<=.35),
        fall=e['shooter_fall_time_s'],max_tilt_deg=e['shooter_max_tilt_deg'],
        wall_s=r['phase8b2']['wall_s'],simulated_s=r['simulated_s'],state_sha256=r['phase8b2']['final_state_sha256'])
