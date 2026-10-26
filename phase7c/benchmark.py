"""Serial RGB-render/readback benchmark; not native-window FPS or GPU-only time."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent));sys.path.insert(0,str(HERE))
from preview import prepared_world,camera
import mujoco
from presentation import png_write
from phase7c.visual_scene import EnhancedScene,prepare_model
from phase7c.integrity import model_signature,save

def main():
    p=argparse.ArgumentParser();p.add_argument('--frames',type=int,default=20)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.frames<5:raise ValueError('At least 5 measured frames per pass required')
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New benchmark output inside phase7c required')
    a.output.mkdir(parents=True)
    modes=[('7b',0,'medium'),('7c_medium',3,'medium'),('7c_low',3,'low'),('7c_none',3,'none')]
    rows=[]
    # Reverse pass controls order effects; each mode gets its own original model.
    for iteration in range(2):
        for name,stage,lod in (modes if iteration==0 else reversed(modes)):
            m,d,source=prepared_world();before=model_signature(m)
            state=d.qpos.tobytes()+d.qvel.tobytes()
            scene=EnhancedScene(m,stage,lod);prepare_model(m,stage)
            scene.update_status({'penalty':1,'total':5,'goals':0,'saves':0})
            updates=[];renders=[]
            with mujoco.Renderer(m,height=640,width=960) as renderer:
                cam=camera('behind')
                for i in range(3+a.frames):
                    begin=time.perf_counter()
                    renderer.update_scene(d,camera=cam);scene.populate(renderer.scene,replace=False)
                    middle=time.perf_counter();pixels=renderer.render();end=time.perf_counter()
                    if i>=3:updates.append(middle-begin);renders.append(end-middle)
                if iteration==0:png_write(a.output/f'{name}.png',pixels)
            assert before==model_signature(m) and state==d.qpos.tobytes()+d.qvel.tobytes()
            row={'mode':name,'pass':iteration+1,'visual_geoms':len(scene.primitives),
                 'update_ms':[s*1000 for s in updates],'render_readback_ms':[s*1000 for s in renders],
                 'physics_unchanged':True,'physical_steps':0}
            rows.append(row)
            print(f'{name}, pass {iteration+1}: update {statistics.mean(updates)*1000:.2f} ms; RGB render/readback {statistics.mean(renders)*1000:.2f} ms',flush=True)
    summary=[]
    for name,_,_ in modes:
        items=[r for r in rows if r['mode']==name]
        updates=sum((r['update_ms'] for r in items),[]);renders=sum((r['render_readback_ms'] for r in items),[])
        totals=[u+r for u,r in zip(updates,renders)]
        summary.append({'mode':name,'visual_geoms':items[0]['visual_geoms'],'measured_frames':len(totals),
            'update_mean_ms':statistics.mean(updates),'render_readback_mean_ms':statistics.mean(renders),
            'total_mean_ms':statistics.mean(totals),'total_median_ms':statistics.median(totals),
            'total_min_ms':min(totals),'total_max_ms':max(totals)})
    save(a.output/'report.json',{'resolution':[960,640],'camera':'same behind camera for all modes',
        'warmup_frames_per_pass':3,'passes':2,'serial':True,'summary':summary,'samples':rows,
        'note':'Includes CPU scene building, draw and RGB readback. Static prepared state; no physics steps. Not native viewer FPS, GPU-only timing or game latency.'})
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
