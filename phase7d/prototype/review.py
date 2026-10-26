"""Matched before/after renders and RGB timing; no game or physical stepping."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parents[1]
sys.path.insert(0,str(PROJECT))
from phase7d.prototype.preview import prepared_world,png_write,camera,model_signature,sources
from phase7d.prototype.stadium import BowlScene,prepare
from phase7d.prototype.revision import RevisedBowl,prepare_revision
import mujoco
import numpy as np

def state(m,d):
    result=np.empty(mujoco.mj_stateSize(m,mujoco.mjtState.mjSTATE_INTEGRATION))
    mujoco.mj_getState(m,d,result,mujoco.mjtState.mjSTATE_INTEGRATION)
    return result.tobytes()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frames',type=int,default=20);a=p.parse_args()
    out=a.output.resolve()
    if out.exists() or not out.is_relative_to(HERE.parent) or a.frames<1:raise ValueError('New phase7d output; frames>=1 required')
    out.mkdir(parents=True)
    protected=sources()
    baseline={str(HERE/f):hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in ('stadium.py','preview.py','test_prototype.py')}
    worlds={};result={}
    try:
        for name,prep,cls in [('previous',prepare,BowlScene),('revised',prepare_revision,RevisedBowl)]:
            m,d,source=prepared_world();signature=model_signature(m);initial=state(m,d)
            prep(m);s=cls(m);r=mujoco.Renderer(m,height=640,width=960)
            worlds[name]=(m,d,s,r,signature,initial)
            for overview in (False,True):
                cam=camera(overview)
                if overview:
                    # Closer elevated view, shared by both variants.
                    cam.lookat[:]=[-4,0,7];cam.distance=78;cam.azimuth=15;cam.elevation=-43
                r.update_scene(d,camera=cam);s.populate(r.scene,replace=False)
                png_write(out/f'{name}_{"overview" if overview else "behind"}.png',r.render())
            result[name]={'custom_geoms':len(s.primitives),'times_seconds':[],
                          'model_counts':signature['counts'],'state_source':str(source),
                          'state_sha256':hashlib.sha256(initial).hexdigest()}
        def draw(name):
            m,d,s,r,*_=worlds[name]
            r.update_scene(d,camera=camera());s.populate(r.scene,replace=False);return r.render()
        for name in worlds:
            for _ in range(4):draw(name)
        for order in (tuple(worlds),tuple(reversed(worlds))):
            for name in order:
                for _ in range(a.frames):
                    start=time.perf_counter();draw(name)
                    result[name]['times_seconds'].append(time.perf_counter()-start)
        for name,(m,d,s,r,signature,initial) in worlds.items():
            assert signature==model_signature(m)
            assert initial==state(m,d)
            times=np.array(result[name]['times_seconds'])*1000
            result[name].update(mean_ms=float(times.mean()),median_ms=float(np.median(times)),
                                min_ms=float(times.min()),max_ms=float(times.max()),
                                physical_signature_unchanged=True,full_state_unchanged=True,physical_steps=0)
        assert protected==sources()
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in baseline.items())
        result['method']={'resolution':[960,640],'warmup':4,'passes':2,'frames_per_pass':a.frames,
                          'includes':'update_scene + populate + render + RGB readback',
                          'excluded':'policy, game, native-viewer FPS',
                          'previous_prototype_files_unchanged':baseline,'protected_source_count':len(protected)}
        (out/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v['mean_ms'] for k,v in result.items() if 'mean_ms' in v}))
    finally:
        for _,_,_,r,*_ in worlds.values():r.close()

if __name__=='__main__':main()
