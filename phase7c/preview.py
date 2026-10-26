"""Actual MuJoCo RGB renders of the saved prepared state; no policy or stepping."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT));sys.path.insert(0,str(PROJECT/'phase3a'))
sys.path.insert(0,str(PROJECT/'phase6a'))
sys.path.insert(0,str(PROJECT/'phase6b'))
import mujoco
import numpy as np
from lateral_scene import build_scene,Limits
from presentation import png_write
from phase7c.visual_scene import EnhancedScene,prepare_model
from phase7c.cameras import specification
from phase7c.integrity import model_signature,save

def prepared_world():
    m,d,*_=build_scene(PROJECT.parent/'RoboNaldo_Deploy',PROJECT.parent/'unitree_mujoco',Limits())
    source=PROJECT/'phase7b/results/final_headless/match_001/penalty_01/physical.json'
    state=json.loads(source.read_text(encoding='utf-8'))['initial_state']
    d.qpos[:]=state['qpos'];d.qvel[:]=state['qvel'];mujoco.mj_forward(m,d)
    return m,d,source

def camera(name):
    spec=specification(name);cam=mujoco.MjvCamera();mujoco.mjv_defaultCamera(cam)
    cam.lookat[:]=spec['lookat'];cam.distance=spec['distance']
    cam.azimuth=spec['azimuth'];cam.elevation=spec['elevation'];return cam

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=int,choices=range(4),default=1)
    p.add_argument('--lod',choices=['none','low','medium'],default='medium')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New output inside phase7c required')
    a.output.mkdir(parents=True)
    m,d,source=prepared_world();signature=model_signature(m)
    before=d.qpos.tobytes()+d.qvel.tobytes()
    scene=EnhancedScene(m,a.stage,a.lod);changes=prepare_model(m,a.stage)
    scene.update_status({'penalty':1,'total':5,'goals':0,'saves':0})
    with mujoco.Renderer(m,height=640,width=960) as renderer:
        for name in ('behind','execution','overview','goal'):
            renderer.update_scene(d,camera=camera(name));scene.populate(renderer.scene,replace=False)
            png_write(a.output/f'{name}.png',renderer.render())
    assert signature==model_signature(m)
    assert before==d.qpos.tobytes()+d.qvel.tobytes()
    save(a.output/'preview.json',{'stage':a.stage,'lod':a.lod,'physical_signature_unchanged':True,
         'state_unchanged':True,'physical_steps':0,'saved_initial_state_source':str(source),
         'saved_initial_state_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'visual_geoms':len(scene.primitives),'appearance_changes':changes})
    print('Rendered real MuJoCo views; no physics steps; physical signature unchanged')

if __name__=='__main__':main()
