"""Unchanged 6B game, 7D stadium, 8B.2 catalog/utility and keeper B, new body PD."""
from bootstrap import *
import argparse
from dataclasses import replace
import functools
import importlib.util
import json
import queue
from phase8b2.catalog import ShotCatalog
from phase8b3.runtime import components

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--posture',choices=['historical','dynamic'],default='dynamic')
    p.add_argument('--lod',choices=['none','low','medium'],default='medium');p.add_argument('--no-decoration',action='store_true')
    p.add_argument('--camera',choices=['behind','execution','overview','goal','follow'],default='behind')
    p.add_argument('--capture-frame',action='store_true');p.add_argument('--autostart',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--distance',choices=['long'],default='long');a,args=p.parse_known_args()
    if '--help' in args or '-h' in args:p.print_help()
    if not a.output or a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New phase8b3 output required')
    args+=['--output',str(a.output),'--distance','long']
    spec=importlib.util.spec_from_file_location('phase8b3_session',PROJECT/'phase6b/run_session.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    from phase7d.presentation import MonumentalPresenter
    from phase7d.cameras import CameraBus
    catalog=ShotCatalog(PROJECT/'phase8b2/catalog_v1.json');Runtime,Selector=components(catalog,a.posture)
    class Match(launcher.CommandMatch):
        def __init__(self,*args,**kwargs):super().__init__(*args,selector=Selector(),calibration=catalog.calibration,**kwargs)
    class Evidence(MonumentalPresenter):
        def after_step(self):
            super().after_step()
            if self.handle is None or not self.config.capture_frame or self.runtime.posture is None:return
            done=self.__dict__.setdefault('captured_postures',set())
            for label in self.runtime.posture.snapshots:
                if label.startswith('sequence_'):continue
                if label not in done:
                    done.add(label);self.render_views(label)
    launcher.VisualRuntime=Runtime;launcher.CommandMatch=Match;launcher.HERE=HERE
    cameras=queue.Queue(16);launcher.CommandBus=functools.partial(CameraBus,camera_requests=cameras)
    launcher.CommandPresenter=lambda r,c,o,d:Evidence(r,replace(c,capture_frame=a.capture_frame),o,d,
        lod='none' if a.no_decoration else a.lod,camera=a.camera,camera_requests=cameras)
    if '--model' not in args:args+=['--model',str(PROJECT/'phase6b/models/whisper-tiny')]
    if a.autostart:
        old=launcher.text_worker
        def auto(bus):bus.submit('Iniciar partido','autostart-text');return old(bus)
        launcher.text_worker=auto
        if '--once' not in args:args.append('--once')
    sys.argv=[str(HERE/'run_session.py'),*args];launcher.main()
if __name__=='__main__':main()
