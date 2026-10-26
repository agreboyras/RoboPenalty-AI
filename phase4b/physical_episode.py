"""Pre-shot selector hook around the unchanged owned phase-4A physical runner."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
from striker_agent import StrikerAgent, InitialObservation
from catalog import CATALOG, load_calibration, classify_after_episode

def save_new(path,value):
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2)

def run(a):
    output=Path(a.output).resolve()
    if not output.is_relative_to(PROJECT) or output.exists():
        raise ValueError('Episode directory must be new and inside RoboPenalty')
    output.mkdir(parents=True)
    old={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
         for phase in ('phase2','phase3a','phase3b','phase4a') for p in (PROJECT/phase).glob('*.py')}
    initial_state=json.loads(Path(a.state).read_text(encoding='utf-8')) if a.state else None
    selector=StrikerAgent(initial_state)
    calibration=load_calibration(a.distance)
    # The loader strips historical outcomes: the selector sees only labeled prior geometry.
    sys.path.insert(0,str(PROJECT/'phase4a'))
    spec=importlib.util.spec_from_file_location('phase4a_physics',PROJECT/'phase4a/experiment.py')
    engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    engine.SCENARIOS={name:dict(config) for name,config in engine.SCENARIOS.items()}
    original_initialize=engine.initialize
    engine_args=argparse.Namespace(output=str(output/'physical.json'),
        mode=a.opponent,scenario=CATALOG[a.distance]['center'][0],duration=14.)
    selection={}

    def before_first_step(config,model,data,kick,rail,probe):
        original_initialize(config,model,data,kick,rail,probe)
        engine.mujoco.mj_forward(model,data)
        if data.time != 0: raise AssertionError('Selection must precede physics')
        pelvis=model.body('gk/pelvis').id
        ball_joint=int(model.body_jntadr[model.body('ball').id])
        ball_q=int(model.jnt_qposadr[ball_joint])
        radius=float(model.geom_size[model.geom('ball_geom').id,0])
        keeper_y=float(data.xpos[pelvis,1])
        half_span=0.
        plane=float(model.body_pos[rail.carriage,0])-.2
        ball_geom=model.geom('ball_geom').id
        for geom in range(model.ngeom):
            if not (model.geom(geom).name or '').startswith('gk/'): continue
            if not (int(model.geom_contype[geom]) & int(model.geom_conaffinity[ball_geom]) or
                    int(model.geom_contype[ball_geom]) & int(model.geom_conaffinity[geom])): continue
            rotation=data.geom_xmat[geom].reshape(3,3)
            center=data.geom_xpos[geom]+rotation@model.geom_aabb[geom,:3]
            extent=abs(rotation)@model.geom_aabb[geom,3:]
            if abs(center[0]-plane)<=extent[0]+radius and abs(center[2]-radius)<=extent[2]+radius:
                half_span=max(half_span,abs(float(center[1]-keeper_y))+float(extent[1]))
        obs=InitialObservation(a.distance,a.opponent,keeper_y,float(data.qpos[rail.qpos]),
            float(data.qvel[rail.dof]),half_span,radius,
            tuple(float(x) for x in data.qpos[ball_q:ball_q+3]),
            tuple(float(x) for x in data.qpos[kick.root_q:kick.root_q+3]))
        before=selector.snapshot()
        decision=selector.choose(obs,calibration,a.episode_id,a.strategy,a.seed,a.fixed_action)
        scenario,bias=CATALOG[a.distance][decision['action']]
        execution=dict(engine.SCENARIOS[scenario])
        # All catalog entries at a given distance differ ONLY in target_y_bias.
        if {k:v for k,v in execution.items() if k!='target_bias'} != {k:v for k,v in config.items() if k!='target_bias'}:
            raise AssertionError('An action cannot silently change initial geometry')
        config.clear(); config.update(execution)  # Owned in-memory metadata copy only.
        engine_args.scenario=scenario
        decision.update(selected_scenario=scenario,execution_configuration=execution,
                        selection_time_sim_s=float(data.time),selection_monotonic_ns=time.monotonic_ns(),
                        statistics_before=before,calibration=calibration)
        save_new(output/'decision_before_shot.json',decision)
        save_new(output/'state_pending.json',selector.snapshot())
        kick.state.target_y_bias=bias  # Existing runtime input; policy/weights remain untouched.
        selection.update(decision)

    engine.initialize=before_first_step
    started=time.perf_counter()
    status=engine.run(engine_args)
    wall=time.perf_counter()-started
    physical=json.loads((output/'physical.json').read_text(encoding='utf-8'))
    if status or not physical['passed']: raise RuntimeError('Physical trial failed; no learning update')
    outcome,prefix_error=classify_after_episode(physical,a.distance,selection['action'])
    # Invalid/unresolved trials throw here and retain their pending audit trail.
    update=selector.observe(a.episode_id,outcome)
    changed=[p for p,h in old.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    if changed: raise AssertionError(f'Previous phase changed: {changed}')
    feedback={'outcome':outcome,'update':update,'feedback_time_sim_s':physical['simulated_s'],
              'feedback_monotonic_ns':time.monotonic_ns(), 'initial_state_sha256':physical['initial_state_sha256'],
              'ball_prefix_error_vs_historical_probe':prefix_error,'prior_sources_checked':len(old),
              'prior_sources_changed':changed,'physical_run_call_wall_s':wall}
    save_new(output/'feedback_after_shot.json',feedback)
    save_new(output/'state_after.json',selector.snapshot())
    print(json.dumps({'episode':a.episode_id,'strategy':a.strategy,'opponent':a.opponent,
                      'action':selection['action'],'outcome':outcome,'physical_run_call_wall_s':wall}))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--strategy',choices=['fixed','random','utility'],default='utility')
    p.add_argument('--opponent',choices=['fixed','agent'],default='agent')
    p.add_argument('--distance',choices=['original','long'],default='long')
    p.add_argument('--fixed-action',choices=['center','left','right'],default='center')
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--state')
    p.add_argument('--episode-id',required=True)
    p.add_argument('--output',required=True)
    run(p.parse_args())

if __name__=='__main__':main()
