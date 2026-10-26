"""Fresh-process physical reference using the original phase-4A runner."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'phase4a'))
sys.path.insert(0,str(PROJECT/'phase4b'))
from catalog import CATALOG, classify_after_episode

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--action',choices=['center','left','right'],required=True)
    p.add_argument('--keeper',choices=['fixed','agent'],default='agent')
    p.add_argument('--distance',choices=['original','long'],default='long')
    p.add_argument('--output',required=True)
    a=p.parse_args(); output=Path(a.output).resolve()
    if not output.is_relative_to(PROJECT) or output.exists(): raise ValueError('New output inside RoboPenalty required')
    output.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('phase5_fresh_reference',PROJECT/'phase4a/experiment.py')
    engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    original=engine.build_scene
    scene=[]
    def capture(*args):
        value=original(*args); scene.extend(value); return value
    engine.build_scene=capture
    args=argparse.Namespace(output=str(output/'physical.json'),mode=a.keeper,
        scenario=CATALOG[a.distance][a.action][0],duration=14.)
    if engine.run(args): raise RuntimeError('Reference physics failed')
    m,d=scene[:2]; kind=engine.mujoco.mjtState.mjSTATE_INTEGRATION
    state=engine.np.empty(engine.mujoco.mj_stateSize(m,kind)); engine.mujoco.mj_getState(m,d,state,kind)
    physical=json.loads((output/'physical.json').read_text())
    outcome,error=classify_after_episode(physical,a.distance,a.action)
    result={'action':a.action,'outcome':outcome,'ball_prefix_error':error,
            'final_integration_state':state.tolist(),'final_integration_sha256':hashlib.sha256(state.tobytes()).hexdigest()}
    with (output/'reference.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)

if __name__=='__main__':main()
