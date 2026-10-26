"""Install per-instance factories; prior modules/files/controllers stay intact."""
from dataclasses import asdict
import json
import numpy as np
from phase8b1.planners import LoggedPlanner

class Probe:
    def __init__(self,base,runtime,context):self.base,self.runtime,self.context=base,runtime,context;self.counter=0
    def __getattr__(self,key):return getattr(self.base,key)
    def mj_step(self,m,d,*args,**kwargs):
        result=self.base.mj_step(m,d,*args,**kwargs);self.counter+=1
        ball=m.body('ball').id;bj=int(m.body_jntadr[ball]);bq=int(m.jnt_qposadr[bj])
        x=float(d.qpos[bq]);p=self.context['probe']
        first=x>=4. and 'first_plane_sample' not in p
        if first or (self.counter%10==0 and 3.5<=x<=5.2):
            scratch=self.base.MjData(m);spec=self.base.mjtState.mjSTATE_INTEGRATION
            a=np.empty(self.base.mj_stateSize(m,spec));self.base.mj_getState(m,d,a,spec)
            self.base.mj_setState(m,scratch,a,spec);self.base.mj_forward(m,scratch)
            bid=m.geom('ball_geom').id;distances=[]
            for g in self.runtime.keeper.geoms:
                if not (int(m.geom_contype[g])&int(m.geom_conaffinity[bid]) or int(m.geom_contype[bid])&int(m.geom_conaffinity[g])):continue
                points=np.zeros(6)
                distance=self.base.mj_geomDistance(m,scratch,bid,int(g),2.,points)
                distances.append((float(distance),m.geom(int(g)).name))
            sample=dict(time_s=float(d.time),ball_position_w=d.qpos[bq:bq+3].tolist(),
                        actual_q_m=float(d.qpos[self.runtime.rail.qpos]),distance_m=min(distances)[0],geom=min(distances)[1])
            p.setdefault('surface_samples',[]).append(sample)
            if first:p['first_plane_sample']=sample
        return result

def install(runtime,variant):
    e=runtime.engine;context={'rows':[],'probe':{}};original=e.LateralControl
    class TrackedControl(original):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);context['control']=self
    e.LateralControl=TrackedControl
    e.GoalkeeperAgent=lambda limits:LoggedPlanner(limits,variant,context)
    e.mujoco=Probe(e.mujoco,runtime,context)
    execute=runtime.execute
    def measured(distance,opponent,output,on_prepared,on_shooting):
        context['rows']=[];context['probe']={}
        result,selection,wall=execute(distance,opponent,output,on_prepared,on_shooting)
        telemetry=dict(variant=variant,limits=asdict(e.Limits()),decision_rows=context['rows'],
                       physical_probe=context['probe'],causal_contract='current observation and current reference state only; no files or future ball trace')
        output.parent.joinpath('planning.json').write_text(json.dumps(telemetry,indent=2),encoding='utf-8')
        return result,selection,wall
    runtime.execute=measured
    return runtime
