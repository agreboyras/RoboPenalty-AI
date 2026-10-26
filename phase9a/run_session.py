"""Interactive selection orchestration over the unchanged physical 8C runtime."""
from bootstrap import *
import argparse
from dataclasses import asdict
import json
import time
from audio import AudioConfig,devices
from game import Config
from phase6a.presentation import PresentationConfig,ViewerClosed
from phase7d.presentation import MonumentalPresenter
from phase8c.catalog import Catalog
from phase8c.runtime import components
from phase9a.bus import InputBus
from phase9a.control import Control,HELP
from phase9a.console import ConsoleInput
from phase9a.session import Match,Service,Script,CommandBoundary
from phase9a.voice import VoiceInput

def main():
    start=time.perf_counter();p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['auto','directed'],default='directed');p.add_argument('--viewer',action='store_true')
    p.add_argument('--voice',action='store_true',help='Explicit opt-in: one bounded capture on each directed selection window; no continuous recording')
    p.add_argument('--device',type=int);p.add_argument('--device-name');p.add_argument('--device-hostapi')
    p.add_argument('--model',type=Path,default=PROJECT/'phase6b/models/whisper-tiny')
    p.add_argument('--listen-seconds',type=float,default=6.);p.add_argument('--audio-blocksize',type=int)
    p.add_argument('--asr-threads',type=int,default=2);p.add_argument('--min-rms',type=float,default=.003)
    p.add_argument('--list-devices',action='store_true');p.add_argument('--penalties',type=int,default=5)
    p.add_argument('--seed',type=int,default=2026);p.add_argument('--autostart',action='store_true');p.add_argument('--once',action='store_true')
    p.add_argument('--script',type=Path);p.add_argument('--output',type=Path);p.add_argument('--capture-frame',action='store_true')
    p.add_argument('--no-decoration',action='store_true');p.add_argument('--unpaced',action='store_true')
    a=p.parse_args()
    if a.list_devices:print(json.dumps(devices(),indent=2));return
    if not a.output or a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('Choose NEW output directory inside phase9a')
    a.output.mkdir(parents=True);catalog=Catalog(PROJECT/'phase8c/catalog_v1.json');Runtime,Automatic=components(catalog,'dynamic')
    config=Config(a.penalties,a.seed,'agent','utility','long','center')
    visual=PresentationConfig(a.viewer,30.,not a.unpaced,1.,1.5,.5,2.,a.capture_frame)
    bus=InputBus();control=Control(bus,a.mode);runtime=Runtime();control.emit=lambda *x,**kw:print(*x,file=runtime.console,**kw)
    presenter=voice=console=service=None;matches=[];current=None;failure=None;termination=None;voice_joined=console_joined=None
    try:
        presenter=MonumentalPresenter(runtime,visual,a.output,'long',lod='none' if a.no_decoration else 'medium',camera='behind',camera_requests=bus.camera_requests)
        runtime.attach(presenter);script=Script(json.loads(a.script.read_text(encoding='utf-8'))) if a.script else None
        service=Service(control,runtime,presenter,script);service.voice_on_wait=a.voice;presenter.service=service
        boundary=CommandBoundary(runtime.engine.mujoco,service);runtime.engine.mujoco=boundary
        if a.voice:
            audio=AudioConfig(str(a.model),a.device,a.listen_seconds,a.asr_threads,a.min_rms,a.device_name,a.device_hostapi,a.audio_blocksize)
            voice=VoiceInput(bus,audio,a.output/'voice');control.voice=voice;voice.start()
        if not a.script:console=ConsoleInput(bus,runtime.console);console.start()
        print(f'READY | Modo {a.mode.upper()} | {HELP}',flush=True)
        presenter.set_status({'phase':'READY','total':config.penalties})
        if a.autostart:bus.submit('Iniciar partido','startup-text')
        while True:
            service.idle()
            if control.reset_requested:control.reset();presenter.set_status({'phase':'READY','total':config.penalties})
            if control.stop_requested:termination='stop';break
            if not control.start_requested:continue
            control.start_requested=False;control.active=True
            match_config=config
            if control.five_requested:
                from dataclasses import replace
                match_config=replace(config,penalties=5);control.five_requested=False
            folder=a.output/f'match_{len(matches)+1:03d}';folder.mkdir()
            current=Match(match_config,runtime,folder,automatic=Automatic(),calibration=catalog.calibration,presenter=presenter,service=service)
            result=current.play()
            (folder/'selection.json').write_text(json.dumps(dict(manual_history=current.router.manual_history,
                waits=current.router.waits,automatic_statistics=current.router.snapshot()),indent=2),encoding='utf-8')
            matches.append(dict(directory=str(folder),phase=result['phase'],scoreboard=result['scoreboard']))
            control.active=False
            if control.stop_requested:termination='stop';break
            if control.reset_requested:continue
            presenter.pause('finished',visual.end_s)
            if a.once:termination='once';break
            print('FINISHED | Marcador, modo, reiniciar partido o salir',flush=True)
    except (ViewerClosed,KeyboardInterrupt) as exc:
        termination=('viewer_closed' if isinstance(exc,ViewerClosed) else 'keyboard_interrupt')+'_unfinished_penalty_unscored'
        if current:
            (current.output/'interrupted.json').write_text(json.dumps(dict(termination=termination,scoreboard=asdict(current.score),
                automatic_statistics=current.router.snapshot()),indent=2),encoding='utf-8')
    except Exception as exc:
        failure=dict(type=type(exc).__name__,message=str(exc));raise
    finally:
        control.close_selection()
        if console:console_joined=console.close()
        if voice:voice_joined=voice.close()
        if presenter:presenter.close()
        report=dict(mode_initial=a.mode,matches=matches,commands=control.events,termination=termination,failure=failure,
            physics_steps=boundary.steps if service else 0,runtime=runtime.summary(),presentation=presenter.summary() if presenter else None,
            control_pauses=service.pause_records if service else [],voice_enabled=a.voice,voice_worker_joined=voice_joined,
            console_worker_joined=console_joined,voice_metrics=voice.metrics if voice else [],script_wall_s=time.perf_counter()-start,
            catalog_sha256=catalog.id,keeper_information_contract='Unchanged 8C runtime; only ObservationReader physical observations. Router/bus/text/action selection not passed to keeper.')
        (a.output/'session.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if voice_joined is False or console_joined is False:raise RuntimeError('An input worker did not close')
    print(f'Sesion 9A cerrada | pasos {report["physics_steps"]} | real {report["script_wall_s"]:.3f}s',flush=True)
if __name__=='__main__':main()
