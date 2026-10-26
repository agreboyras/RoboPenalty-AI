"""Calibrated action catalog + unchanged keeper B + unchanged 7D stadium/game."""
from bootstrap import *
import argparse
from dataclasses import replace
import functools
import importlib.util
import json
import queue
from phase8b2.catalog import ShotCatalog
from phase8b2.runtime import components
from phase8b2.integrity import protected_sources

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--catalog',type=Path,default=HERE/'catalog_v1.json')
    p.add_argument('--historical-reference',choices=['A','B'],help='Validation only: original three-action catalog and selector')
    p.add_argument('--lod',choices=['none','low','medium'],default='medium')
    p.add_argument('--no-decoration',action='store_true')
    p.add_argument('--camera',choices=['behind','execution','overview','goal','follow'],default='behind')
    p.add_argument('--capture-frame',action='store_true');p.add_argument('--autostart',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--distance',choices=['long'],default='long')
    a,args=p.parse_known_args()
    if '--help' in args or '-h' in args:p.print_help()
    if a.output:
        if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New phase8b2 output required')
        args+=['--output',str(a.output)]
    elif '--help' not in args and '-h' not in args:p.error('--output required')
    args+=['--distance','long']
    spec=importlib.util.spec_from_file_location('phase8b2_session',PROJECT/'phase6b/run_session.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    from phase8b1.runtime_adapter import install
    from phase7d.presentation import MonumentalPresenter
    from phase7d.cameras import CameraBus
    catalog=None if a.historical_reference else ShotCatalog(a.catalog)
    if catalog:Runtime,Selector=components(catalog)
    else:Runtime=launcher.VisualRuntime
    class ExperimentalRuntime(Runtime):
        def __init__(self):super().__init__();install(self,a.historical_reference or 'B')
    class ExperimentalMatch(launcher.CommandMatch):
        def __init__(self,*args,**kwargs):
            if catalog:kwargs.update(selector=Selector(),calibration=catalog.calibration)
            super().__init__(*args,**kwargs)
    class EvidencePresenter(MonumentalPresenter):
        interception_captured=False
        def after_step(self):
            super().after_step()
            if self.handle is None or not self.config.capture_frame:return
            ball=self.runtime.model.body('ball').id
            if self.status.get('penalty')==1 and self.runtime.data.xpos[ball,0]>=3.85 and not self.interception_captured:
                self.interception_captured=True;self.render_views('interception')
            action=self.status.get('action') or ''
            captured=self.__dict__.setdefault('corner_captures',{})
            if action.startswith('corner_') and self.runtime.data.xpos[ball,0]>=4.95 and action not in captured:
                captured[action]={'time_s':float(self.runtime.data.time),'ball_position_w':self.runtime.data.xpos[ball].tolist()}
                self.render_views(action)
        def summary(self):return {**super().summary(),'corner_captures':self.__dict__.get('corner_captures',{})}
    launcher.VisualRuntime=ExperimentalRuntime;launcher.CommandMatch=ExperimentalMatch;launcher.HERE=HERE
    cameras=queue.Queue(16);launcher.CommandBus=functools.partial(CameraBus,camera_requests=cameras)
    launcher.CommandPresenter=lambda runtime,config,output,distance:EvidencePresenter(runtime,
        replace(config,capture_frame=a.capture_frame),output,distance,
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
        after=protected_sources();changed=[key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)]
        if a.output and a.output.is_dir():
            (a.output/'protected_sources.json').write_text(json.dumps(dict(checked=len(before),changed=changed),indent=2),encoding='utf-8')
            report=a.output/'session.json'
            if report.exists():
                data=json.loads(report.read_text(encoding='utf-8'))
                data['phase8b2']={'catalog_sha256':catalog.id if catalog else None,
                    'actions':catalog.actions if catalog else ['center','left','right'],
                    'keeper_planner':a.historical_reference or 'B','historical_validation_only':bool(a.historical_reference)}
                report.write_text(json.dumps(data,indent=2),encoding='utf-8')
        if changed:raise RuntimeError(changed)
if __name__=='__main__':main()
