"""CLI: one Python process, one scene and ONNX session, multiple penalties."""
import time
START=time.perf_counter()
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
from game import Config, Match

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--penalties',type=int,default=5)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--keeper',choices=['fixed','agent'],default='agent')
    p.add_argument('--striker',choices=['fixed','random','utility'],default='utility')
    p.add_argument('--distance',choices=['original','long'],default='long')
    p.add_argument('--fixed-action',choices=['center','left','right'],default='center')
    p.add_argument('--output',required=True)
    a=p.parse_args(); config=Config(a.penalties,a.seed,a.keeper,a.striker,a.distance,a.fixed_action)
    output=Path(a.output).resolve()
    if not output.is_relative_to(PROJECT) or output.exists(): raise ValueError('Choose a new directory inside RoboPenalty')
    output.mkdir(parents=True)
    previous={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for phase in ('phase2','phase3a','phase3b','phase4a','phase4b') for f in (PROJECT/phase).glob('*.py')}
    from runtime import SimulationRuntime
    print(f'RoboPenalty | {config.penalties} penales | delantero {config.striker} | arquero {config.keeper} | distancia {config.distance} | seed {config.seed}',flush=True)
    runtime=SimulationRuntime()
    result=Match(config,runtime,output).play()
    changed=[f for f,h in previous.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h]
    if changed: raise RuntimeError(f'Previous source files changed: {changed}')
    verification={'script_wall_s':time.perf_counter()-START,'previous_sources_checked':len(previous),
                  'previous_sources_changed':changed,'finished':result['phase']=='FINISHED',
                  'python_pid':os.getpid(),'model_builds':runtime.model_builds,'policy_loads':runtime.policy_loads}
    with (output/'verification.json').open('x',encoding='utf-8') as f: json.dump(verification,f,indent=2)
    score=result['scoreboard']
    print(f'FINISHED | {score["goals"]} goles, {score["saves"]} atajadas, {score["misses"]} errados | total real {verification["script_wall_s"]:.3f}s',flush=True)

if __name__=='__main__':main()
