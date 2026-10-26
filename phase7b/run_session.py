"""Delegate the complete 6B session; inject only a visual presenter locally."""
import argparse
from dataclasses import replace
import functools
import importlib.util
from pathlib import Path
import sys
import queue

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT/'phase6b'))

def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('--stage', type=int, choices=range(1,7), default=6)
    p.add_argument('--no-decoration', action='store_true')
    p.add_argument('--camera', choices=['execution','overview','goal','follow'], default='execution')
    p.add_argument('--autostart', action='store_true')
    p.add_argument('--capture-frame', action='store_true')
    p.add_argument('--distance',choices=['long'],default='long',help='Adapted marks support only the validated 6 m setup')
    p.add_argument('--output',type=Path)
    a, forwarded = p.parse_known_args()
    if '--help' in forwarded or '-h' in forwarded:
        print('Opciones adicionales de la variante visual 7B:')
        p.print_help()
    if a.output:
        if not a.output.resolve().is_relative_to(HERE) or a.output.exists():
            p.error('--output must be a NEW directory inside phase7b')
        forwarded.extend(['--output',str(a.output)])
    forwarded.extend(['--distance',a.distance])
    spec = importlib.util.spec_from_file_location('phase7b_existing_session', PROJECT/'phase6b/run_session.py')
    launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
    from phase7b.presentation import StadiumPresenter
    from phase7b.cameras import ViewCommandBus
    from phase7b.integrity import protected_sources, save
    before = protected_sources()
    # Local module bindings only: no earlier source file or orchestrator is edited.
    launcher.HERE = HERE
    camera_requests=queue.Queue(maxsize=16)
    launcher.CommandBus=functools.partial(ViewCommandBus,camera_requests=camera_requests)
    def presenter(runtime,config,output,distance):
        return StadiumPresenter(runtime,replace(config,capture_frame=a.capture_frame),output,distance,
            stage=a.stage,decoration=not a.no_decoration,camera=a.camera,camera_requests=camera_requests)
    launcher.CommandPresenter = presenter
    if '--model' not in forwarded:
        forwarded.extend(['--model',str(PROJECT/'phase6b/models/whisper-tiny')])
    if a.autostart:
        if '--script' in forwarded: p.error('--autostart and --script are mutually exclusive')
        original_text_worker=launcher.text_worker
        def auto_text_worker(bus):
            bus.submit('Iniciar partido','autostart-text')
            # Keep interactive text controls even when starting automatically.
            return original_text_worker(bus)
        launcher.text_worker=auto_text_worker
        if '--once' not in forwarded: forwarded.append('--once')
    sys.argv = [str(HERE/'run_session.py'), *forwarded]
    if a.stage>=5:print('CAMARAS | /cam execution | /cam overview | /cam goal | /cam follow',flush=True)
    try:
        launcher.main()
    finally:
        after = protected_sources()
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        if '--output' in forwarded:
            out = Path(forwarded[forwarded.index('--output')+1]).resolve()
            if out.is_relative_to(HERE) and out.is_dir():
                save(out/'protected_sources.json', {'checked':len(before),'changed':changed,'before':before,'after':after})
        if changed: raise RuntimeError(f'Protected source files changed: {changed}')

if __name__ == '__main__': main()
