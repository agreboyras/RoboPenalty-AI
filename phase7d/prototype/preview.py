"""Render and benchmark isolated 7D proposal against unchanged 7C."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
sys.path.insert(0,str(PROJECT))
from phase7c.preview import prepared_world,png_write
from phase7c.visual_scene import EnhancedScene,prepare_model
from phase7c.integrity import model_signature,protected_sources
from phase7d.prototype.stadium import BowlScene,prepare
import mujoco
import numpy as np

def camera(overview=False):
    c=mujoco.MjvCamera();mujoco.mjv_defaultCamera(c)
    c.lookat[:]=[-3,0,6] if overview else [2.7,0,2.8]
    c.distance=100 if overview else 11.8
    c.azimuth=-90 if overview else 15
    c.elevation=-50 if overview else 5
    return c

def sources():
    files={p:h for p,h in protected_sources().items() if not Path(p).is_relative_to(HERE.parent)}
    for p in (PROJECT/'phase7c').rglob('*'):
        if p.is_file() and not {'results','__pycache__'}.intersection(p.relative_to(PROJECT/'phase7c').parts):
            files[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return files

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frames',type=int,default=12);a=p.parse_args()
    output=a.output.resolve()
    if not output.is_relative_to(HERE.parent) or output.exists():raise ValueError('New output under phase7d required')
    output.mkdir(parents=True)
    protected=sources();worlds={};results={}
    for name in ('7c','prototype','no_decoration'):
        m,d,source=prepared_world();before=model_signature(m)
        state=d.qpos.tobytes()+d.qvel.tobytes()+d.ctrl.tobytes()+d.qacc_warmstart.tobytes()
        if name=='7c':prepare_model(m,3);scene=EnhancedScene(m,3,'medium')
        else:prepare(m);scene=BowlScene(m,decoration=name!='no_decoration')
        # Matched camera, FOV, clipping and resolution for a fair RGB cost comparison.
        m.vis.global_.fovy=65;m.vis.map.zfar=220
        scene.update_status(dict(goals=0,saves=0,penalty=1,total=5))
        assert before==model_signature(m),'Physical model changed'
        assert len(scene.primitives)<1500,'Prototype geometry budget exceeded'
        renderer=mujoco.Renderer(m,height=640,width=960)
        def draw(r=renderer,data=d,s=scene,cam=camera()):
            r.update_scene(data,camera=cam);s.populate(r.scene,replace=False);return r.render()
        png_write(output/f'{name}_behind.png',draw())
        renderer.update_scene(d,camera=camera(True));scene.populate(renderer.scene,replace=False)
        png_write(output/f'{name}_overview.png',renderer.render())
        for _ in range(3):draw()
        worlds[name]=(renderer,draw,m,d,scene,before,state)
        results[name]={'custom_geoms':len(scene.primitives),'timings_seconds':[],'model_counts':before['counts'],
                       'saved_state_source':str(source),'physical_steps':0}
    try:
        for order in (list(worlds),list(reversed(worlds))):
            for name in order:
                draw=worlds[name][1]
                for _ in range(a.frames):
                    start=time.perf_counter();draw()
                    results[name]['timings_seconds'].append(time.perf_counter()-start)
        for name,(renderer,draw,m,d,scene,before,state) in worlds.items():
            assert before==model_signature(m)
            assert state==d.qpos.tobytes()+d.qvel.tobytes()+d.ctrl.tobytes()+d.qacc_warmstart.tobytes()
            durations=results[name]['timings_seconds']
            results[name].update(mean_ms=float(np.mean(durations)*1000),min_ms=min(durations)*1000,
                                 max_ms=max(durations)*1000,model_unchanged=True,state_unchanged=True)
        assert protected==sources(),'Protected sources changed'
        results['method']={'resolution':[960,640],'passes':2,'frames_per_pass':a.frames,'warmup':3,
                           'includes':'update_scene + custom geometry population + render + RGB readback',
                           'not_measured':'native passive-viewer FPS or gameplay performance',
                           'protected_source_count':len(protected),'sources_unchanged':True}
        (output/'metrics.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps({k:v['mean_ms'] for k,v in results.items() if 'mean_ms' in v}))
    finally:
        for renderer,*_ in worlds.values():renderer.close()

if __name__=='__main__':main()
