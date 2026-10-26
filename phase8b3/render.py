"""Render stored real joint states in the unmodified 7D scene, no simulation steps."""
from bootstrap import *
import argparse
import json
import numpy as np
import mujoco
from lateral_scene import build_scene,Limits
from phase7d.visual_scene import StadiumScene,prepare_model
from phase7d.cameras import specification
from phase6a.presentation import png_write
from phase7c.integrity import model_signature

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True)
    m,d,sh,gk,rail=build_scene(PROJECT.parent/'RoboNaldo_Deploy',PROJECT.parent/'unitree_mujoco',Limits())
    signature=model_signature(m);prepare_model(m);scene=StadiumScene(m,'medium');evidence=[]
    # Same keeper close-up across states and directions, plus the established behind view.
    camera=mujoco.MjvCamera();mujoco.mjv_defaultCamera(camera)
    camera.lookat[:]=[4.2,0,.85];camera.distance=2.6;camera.azimuth=15;camera.elevation=-12
    with mujoco.Renderer(m,height=640,width=960) as renderer:
        for label,path in [('historical_final',PROJECT/'phase8b2/results/agents/B_center_01/physical.json'),
                           ('dynamic_final',a.input/'penalty_05/physical.json')]:
            physical=json.loads(path.read_text());spec=mujoco.mjtState.mjSTATE_INTEGRATION
            mujoco.mj_setState(m,d,np.array(physical['phase5_state']['final_integration_state']),spec);mujoco.mj_forward(m,d)
            scene.update_status(dict(goals=0,saves=0,penalty=5,total=5))
            renderer.update_scene(d,camera=camera);scene.populate(renderer.scene,replace=False)
            png_write(a.output/f'{label}.png',renderer.render())
            evidence.append(dict(file=f'{label}.png',source=str(path),time_s=float(d.time),note='Actual final integrated state at t=14, same camera; board is illustrative'))
        for folder in sorted(a.input.glob('penalty_*')):
            report=json.loads((folder/'posture.json').read_text());physical=json.loads((folder/'physical.json').read_text())
            for label,state in report['snapshots'].items():
                if label.startswith('sequence_') and folder.name!='penalty_05':continue
                d.qpos[:]=state['qpos'];d.qvel[:]=state['qvel'];d.ctrl[:]=state['ctrl'];d.time=state['time_s']
                mujoco.mj_forward(m,d)
                scene.update_status(dict(goals=0,saves=0,penalty=int(folder.name[-2:]),total=5))
                before=d.qpos.tobytes()+d.qvel.tobytes()+d.ctrl.tobytes()
                renderer.update_scene(d,camera=camera);scene.populate(renderer.scene,replace=False)
                path=a.output/f'{folder.name}_{label}.png';png_write(path,renderer.render())
                assert before==d.qpos.tobytes()+d.qvel.tobytes()+d.ctrl.tobytes()
                evidence.append(dict(file=path.name,source=str(folder/'posture.json'),label=label,time_s=state['time_s'],
                    result_observed_after_episode=physical['evaluation']['provisional_outcome_not_save_classification'],
                    note='Actual integrated joint state restored for rendering; zero physical steps; snapshot board is illustrative, not live score'))
    assert signature==model_signature(m)
    (a.output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print('Real MuJoCo renders:',len(evidence))
if __name__=='__main__':main()
