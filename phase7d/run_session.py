"""7D stadium variant; all game, input, agents and physics reused unchanged."""
import argparse
from dataclasses import replace
import functools
import importlib.util
from pathlib import Path
import queue
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT));sys.path.insert(0,str(PROJECT/'phase6b'))

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--lod',choices=['none','low','medium'],default='medium')
    p.add_argument('--no-decoration',action='store_true')
    p.add_argument('--reference-7c',action='store_true',help='Benchmark unchanged 7C presenter; output remains inside 7D')
    p.add_argument('--camera',choices=['behind','execution','overview','goal','follow'],default='behind')
    p.add_argument('--capture-frame',action='store_true');p.add_argument('--autostart',action='store_true')
    p.add_argument('--distance',choices=['long'],default='long');p.add_argument('--output',type=Path)
    a,args=p.parse_known_args()
    if '--help' in args or '-h' in args:p.print_help()
    if not a.output and '--help' not in args and '-h' not in args:p.error('--output required')
    if a.output:
        if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output inside phase7d required')
        args+=['--output',str(a.output)]
    args+=['--distance','long']
    spec=importlib.util.spec_from_file_location('phase7d_existing_session',PROJECT/'phase6b/run_session.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    from phase7d.presentation import MonumentalPresenter
    from phase7d.cameras import CameraBus
    from phase7d.integrity import protected_sources,save
    before=protected_sources();requests=queue.Queue(16)
    launcher.HERE=HERE
    launcher.CommandBus=functools.partial(CameraBus,camera_requests=requests)
    if a.reference_7c:
        from phase7c.presentation import EnhancedPresenter
        launcher.CommandPresenter=lambda runtime,config,output,distance:EnhancedPresenter(
            runtime,replace(config,capture_frame=a.capture_frame),output,distance,enhancement_stage=3,
            lod='none' if a.no_decoration else a.lod,camera=a.camera,camera_requests=requests)
    else:
        launcher.CommandPresenter=lambda runtime,config,output,distance:MonumentalPresenter(
            runtime,replace(config,capture_frame=a.capture_frame),output,distance,
            lod='none' if a.no_decoration else a.lod,camera=a.camera,camera_requests=requests)
    if '--model' not in args:args+=['--model',str(PROJECT/'phase6b/models/whisper-tiny')]
    if a.autostart:
        if '--script' in args:p.error('--autostart cannot combine with --script')
        worker=launcher.text_worker
        def auto_worker(bus):bus.submit('Iniciar partido','autostart-text');return worker(bus)
        launcher.text_worker=auto_worker
        if '--once' not in args:args.append('--once')
    sys.argv=[str(HERE/'run_session.py'),*args]
    try:launcher.main()
    finally:
        after=protected_sources();changed=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
        if a.output and a.output.is_dir():save(a.output/'protected_sources.json',dict(checked=len(before),changed=changed))
        if changed:raise RuntimeError(f'Protected sources changed: {changed}')

if __name__=='__main__':main()
