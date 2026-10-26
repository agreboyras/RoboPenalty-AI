"""Local Spanish commands driving the existing RoboPenalty orchestrator."""
import time
START = time.perf_counter()
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
from commands import CommandBus
from control import Control
from audio import AudioConfig, VoiceWorker, text_worker,resolve_input
from audio_trace import AudioTrace,summarize_metrics
from session import VisualRuntime, CommandPresenter, CommandMatch, CommandBoundary, Service, Script
from presentation import PresentationConfig
from game import Config


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--voice', action='store_true'); p.add_argument('--viewer', action='store_true')
    p.add_argument('--model', default=str(HERE/'models/whisper-tiny'))
    p.add_argument('--device', type=int); p.add_argument('--listen-seconds', type=float, default=4.)
    p.add_argument('--device-name',help='Required substring of the selected input name; never substitutes another index')
    p.add_argument('--device-hostapi',help='Required host API, e.g. Windows WASAPI')
    p.add_argument('--audio-diagnostics',action='store_true',help='Save exact session WAVs/decisions under output/audio (opt-in)')
    p.add_argument('--audio-blocksize',type=int,help='Experimental stream blocksize: 0=host default; omission preserves 100 ms')
    p.add_argument('--asr-threads', type=int, default=2)
    p.add_argument('--min-rms', type=float, default=.003)
    p.add_argument('--manual-next', action='store_true'); p.add_argument('--once', action='store_true')
    p.add_argument('--script', type=Path, help='JSON text-command fixture, not audio evidence')
    p.add_argument('--penalties', type=int, default=5); p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--keeper', choices=['fixed','agent'], default='agent')
    p.add_argument('--striker', choices=['fixed','random','utility'], default='utility')
    p.add_argument('--distance', choices=['original','long'], default='long')
    p.add_argument('--fixed-action', choices=['center','left','right'], default='center')
    p.add_argument('--unpaced', action='store_true'); p.add_argument('--fps', type=float, default=30.)
    p.add_argument('--before-shot', type=float, default=1.)
    p.add_argument('--after-result', type=float, default=1.5)
    p.add_argument('--before-reset', type=float, default=.5)
    p.add_argument('--end-pause', type=float, default=2.)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    config = Config(a.penalties,a.seed,a.keeper,a.striker,a.distance,a.fixed_action)
    visual = PresentationConfig(a.viewer,a.fps,not a.unpaced,a.before_shot,a.after_result,a.before_reset,a.end_pause)
    audio_config = AudioConfig(a.model,a.device,a.listen_seconds,a.asr_threads,a.min_rms,a.device_name,a.device_hostapi,a.audio_blocksize)
    output = Path(a.output).resolve()
    if not output.is_relative_to(HERE) or output.exists():
        raise ValueError('Choose a NEW output directory inside phase6b')
    if a.audio_diagnostics and (not a.voice or not output.is_relative_to(HERE/'results')):
        raise ValueError('--audio-diagnostics requires --voice and output inside phase6b/results')
    expected_input=resolve_input(audio_config) if a.voice else None
    if expected_input:
        print(f'ENTRADA VALIDADA | indice={expected_input["index"]} | {expected_input["name"]} | {expected_input["hostapi"]}',flush=True)
    output.mkdir(parents=True)
    trace=AudioTrace(output/'audio') if a.audio_diagnostics else None
    phases = ('phase2','phase3a','phase3b','phase4a','phase4b','phase5','phase6a')
    before = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for phase in phases for f in (PROJECT/phase).glob('*.py')}
    bus = CommandBus(); control = Control(bus,a.manual_next)
    if trace:control.on_command_result=trace.decision
    runtime = VisualRuntime(); initialization = time.perf_counter()-START
    # Earlier physical runners capture stdout; command acknowledgements must stay live.
    control.emit = lambda *args, **kwargs: print(*args, file=runtime.console, **kwargs)
    presenter = None; voice = None; service = None; matches = []
    voice_joined = None; failure = None
    try:
        presenter = CommandPresenter(runtime,visual,output,config.distance)
        runtime.attach(presenter)
        script = Script(json.loads(a.script.read_text(encoding='utf-8'))) if a.script else None
        service = Service(control,runtime,presenter,script)
        presenter.service = service
        boundary = CommandBoundary(runtime.engine.mujoco,service)
        runtime.engine.mujoco = boundary
        if not a.script: text_worker(bus)
        if a.voice:
            voice = VoiceWorker(bus,audio_config,trace=trace,expected_device=expected_input); voice.start()
        print('READY | Texto y voz usan la misma cola. Diga/escriba iniciar partido. Detener partido cierra.',flush=True)
        presenter.set_status({'phase':'READY','total':config.penalties})
        while True:
            service.idle()
            if control.reset_requested:
                control.reset()
                presenter.set_status({'phase':'READY','total':config.penalties})
                print('READY | Nueva tanda, estadisticas reiniciadas; modelo y politica retenidos',flush=True)
            if control.stop_requested: break
            if not control.start_requested: continue
            match_config = replace(config,penalties=5) if control.five_requested else config
            control.start_requested = control.five_requested = False
            control.active = True
            folder = output/f'match_{len(matches)+1:03d}'; folder.mkdir()
            match = CommandMatch(match_config,runtime,folder,presenter=presenter,service=service)
            result = match.play()
            matches.append({'directory':str(folder),'result':result})
            control.active = False
            if control.stop_requested: break
            if control.reset_requested: continue
            presenter.pause('finished',visual.end_s)
            if a.once: break
            print('FINISHED | Mostrar marcador, reiniciar partido o detener partido',flush=True)
    except Exception as exc:
        failure = {'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        if voice: voice_joined = voice.close()
        if trace and voice_joined:trace.finalize()
        if presenter: presenter.close()
        changed = [f for f,h in before.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h]
        audio_metrics=summarize_metrics(voice.metrics if voice else [],control.events,voice_joined)
        report = {'script_wall_s':time.perf_counter()-START,'initialization_before_viewer_s':initialization,
            'matches': [{'directory':m['directory'],'phase':m['result']['phase'],
                         'scoreboard':m['result']['scoreboard']} for m in matches],
            'commands':control.events,'queue_dropped':bus.dropped,'generation':bus.epoch(),
            'control_pauses':service.pause_records if service else [],
            'voice_enabled':a.voice,'audio_metrics':audio_metrics,
            'expected_audio_input':expected_input,'audio_diagnostics':str(trace.directory) if trace else None,
            'audio_worker_joined':voice_joined,'presentation':presenter.summary() if presenter else None,
            'physics_steps':boundary.steps if service else 0,'runtime':runtime.summary(),
            'previous_sources_checked':len(before),'previous_sources_changed':changed,'failure':failure}
        (output/'session.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if changed: raise RuntimeError(f'Previous sources changed: {changed}')
    print(f'Sesion cerrada | real {report["script_wall_s"]:.3f}s | pasos {report["physics_steps"]}',flush=True)


if __name__ == '__main__': main()
