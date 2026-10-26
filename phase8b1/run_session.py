"""Experimental runtime factories plus the unmodified 7D presenter and 6B game."""
import argparse
from dataclasses import replace
import functools
import importlib.util
import json
import queue
from bootstrap import *

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--planner',choices=['A','B','C'],default='B')
    p.add_argument('--lod',choices=['none','low','medium'],default='medium')
    p.add_argument('--no-decoration',action='store_true')
    p.add_argument('--camera',choices=['behind','execution','overview','goal','follow'],default='behind')
    p.add_argument('--capture-frame',action='store_true');p.add_argument('--autostart',action='store_true')
    p.add_argument('--distance',choices=['long'],default='long');p.add_argument('--output',type=Path)
    a,args=p.parse_known_args()
    if '--help' in args or '-h' in args:p.print_help()
    if a.output:
        if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New phase8b1 output required')
        args+=['--output',str(a.output)]
    elif '--help' not in args and '-h' not in args:p.error('--output required')
    args+=['--distance','long']
    spec=importlib.util.spec_from_file_location('eight_existing_session',PROJECT/'phase6b/run_session.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    from phase8b1.runtime_adapter import install
    from phase8b1.integrity import protected_sources
    from phase7d.presentation import MonumentalPresenter
    from phase7d.cameras import CameraBus
    class ExperimentalRuntime(launcher.VisualRuntime):
        def __init__(self):super().__init__();install(self,a.planner)
    class EvidencePresenter(MonumentalPresenter):
        interception_evidence=None
        def after_step(self):
            super().after_step()
            if self.handle is None or not self.config.capture_frame or self.interception_evidence is not None:return
            ball=self.runtime.model.body('ball').id
            if self.status.get('penalty')==1 and self.runtime.data.xpos[ball,0]>=3.85:
                self.interception_evidence={'time_sim_s':float(self.runtime.data.time),
                    'keeper_q_m':float(self.runtime.data.qpos[self.runtime.rail.qpos]),
                    'ball_position_w':self.runtime.data.xpos[ball].tolist()}
                self.render_views('interception')
        def summary(self):return {**super().summary(),'phase8b1_capture':self.interception_evidence}
    launcher.VisualRuntime=ExperimentalRuntime;launcher.HERE=HERE
    cameras=queue.Queue(16)
    launcher.CommandBus=functools.partial(CameraBus,camera_requests=cameras)
    launcher.CommandPresenter=lambda runtime,config,output,distance:EvidencePresenter(
        runtime,replace(config,capture_frame=a.capture_frame),output,distance,
        lod='none' if a.no_decoration else a.lod,camera=a.camera,camera_requests=cameras)
    if '--model' not in args:args+=['--model',str(PROJECT/'phase6b/models/whisper-tiny')]
    if a.autostart:
        if '--script' in args:p.error('--autostart cannot combine with --script')
        old=launcher.text_worker
        def auto(bus):bus.submit('Iniciar partido','autostart-text');return old(bus)
        launcher.text_worker=auto
        if '--once' not in args:args.append('--once')
    before=protected_sources();sys.argv=[str(HERE/'run_session.py'),*args]
    try:launcher.main()
    finally:
        after=protected_sources();changed=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
        if a.output and a.output.is_dir():
            (a.output/'protected_sources.json').write_text(json.dumps(dict(checked=len(before),changed=changed),indent=2),encoding='utf-8')
            report=a.output/'session.json'
            if report.exists():
                data=json.loads(report.read_text(encoding='utf-8'));data['phase8b1']={'planner':a.planner,'physics_limits':'unchanged phase3a Limits'}
                report.write_text(json.dumps(data,indent=2),encoding='utf-8')
        if changed:raise RuntimeError(changed)

if __name__=='__main__':main()
