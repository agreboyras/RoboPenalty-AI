"""Native-viewer or headless launcher, reusing phase-5 model/data and agents."""
import time
START=time.perf_counter()
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
from integration import VisualRuntime,VisualMatch
from game import Config
from presentation import Presenter,PresentationConfig,ViewerClosed

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--viewer',action='store_true')
    p.add_argument('--penalties',type=int,default=5);p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--keeper',choices=['fixed','agent'],default='agent')
    p.add_argument('--striker',choices=['fixed','random','utility'],default='utility')
    p.add_argument('--distance',choices=['original','long'],default='long')
    p.add_argument('--fixed-action',choices=['center','left','right'],default='center')
    p.add_argument('--fps',type=float,default=30);p.add_argument('--unpaced',action='store_true')
    p.add_argument('--before-shot',type=float,default=1.);p.add_argument('--after-result',type=float,default=1.5)
    p.add_argument('--before-reset',type=float,default=.5);p.add_argument('--end-pause',type=float,default=3.)
    p.add_argument('--capture-frame',action='store_true');p.add_argument('--output',required=True)
    a=p.parse_args()
    config=Config(a.penalties,a.seed,a.keeper,a.striker,a.distance,a.fixed_action)
    visual=PresentationConfig(a.viewer,a.fps,not a.unpaced,a.before_shot,a.after_result,a.before_reset,a.end_pause,a.capture_frame)
    output=Path(a.output).resolve()
    if not output.is_relative_to(PROJECT) or output.exists():raise ValueError('Choose a new output directory inside RoboPenalty')
    output.mkdir(parents=True)
    before={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for phase in ('phase2','phase3a','phase3b','phase4a','phase4b','phase5') for f in (PROJECT/phase).glob('*.py')}
    print(f'RoboPenalty | {config.penalties} penales | viewer={a.viewer} | {config.striker} vs {config.keeper}',flush=True)
    runtime=VisualRuntime();initialization=time.perf_counter()-START
    presenter=None;result=None;failure=None
    try:
        presenter=Presenter(runtime,visual,output,config.distance);runtime.attach(presenter)
        match=VisualMatch(config,runtime,output,presenter=presenter)
        result=match.play()
        presenter.pause('finished',visual.end_s)
    except Exception as exc:
        failure={'type':type(exc).__name__,'message':str(exc),'cancelled':isinstance(exc,ViewerClosed)}
        raise
    finally:
        if presenter is not None:
            presenter.close();summary=presenter.summary()
            summary['episodes']=presenter.episodes
            if runtime.boundary is not None:
                summary['mj_step_calls']=runtime.boundary.steps
                summary['mj_step_call_wall_s']=runtime.boundary.step_wall_s
            (output/'presentation.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        if failure:(output/'failure.json').write_text(json.dumps(failure,indent=2),encoding='utf-8')
    changed=[f for f,h in before.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h]
    if changed:raise RuntimeError(f'Previous sources changed: {changed}')
    verify={'finished':result['phase']=='FINISHED','viewer':a.viewer,'initialization_before_viewer_s':initialization,
        'runtime_setup_wall_s':runtime.setup_wall_s,'script_wall_s':time.perf_counter()-START,
        'previous_sources_checked':len(before),'previous_sources_changed':changed,'pid':os.getpid(),
        'model_builds':runtime.model_builds,'policy_loads':runtime.policy_loads,'viewer_closed':presenter.closed}
    (output/'verification.json').write_text(json.dumps(verify,indent=2),encoding='utf-8')
    score=result['scoreboard']
    print(f'FINISHED | {score["goals"]} goles / {score["saves"]} atajadas / {score["misses"]} errados | total real {verify["script_wall_s"]:.3f}s',flush=True)

if __name__=='__main__':main()
