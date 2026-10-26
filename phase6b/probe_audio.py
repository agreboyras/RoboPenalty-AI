"""Read-only device discovery and bounded real capture/transcription diagnostic."""
import argparse
import json
from pathlib import Path
import threading
import time
from audio import AudioConfig, VoiceWorker, capture, devices
from commands import CommandBus


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--list-devices',action='store_true'); p.add_argument('--capture-only',action='store_true')
    p.add_argument('--model',default=str(Path(__file__).resolve().parent/'models/whisper-tiny'))
    p.add_argument('--device',type=int); p.add_argument('--listen-seconds',type=float,default=4.)
    p.add_argument('--min-rms',type=float,default=.003)
    p.add_argument('--output',type=Path)
    a = p.parse_args()
    if a.output and (a.output.exists() or not a.output.resolve().is_relative_to(Path(__file__).resolve().parent)):
        raise ValueError('New output file inside phase6b required')
    report = {'devices':devices()}
    print(json.dumps(report,indent=2),flush=True)
    if not a.list_devices:
        config = AudioConfig(a.model,a.device,a.listen_seconds,min_rms=a.min_rms)
        if a.capture_only:
            start = time.perf_counter(); data,rms = capture(config,threading.Event())
            report['capture'] = {'samples':len(data),'rms':rms,'wall_s':time.perf_counter()-start,
                                 'speech_verified':False}
        else:
            bus = CommandBus(); worker = VoiceWorker(bus,config,once=True); worker.start()
            while worker.thread.is_alive():
                while (m := bus.drain()) is not None: print(f'{m.kind}: {m.text} -> {m.intent}',flush=True)
                worker.thread.join(.1)
            while (m := bus.drain()) is not None: print(f'{m.kind}: {m.text} -> {m.intent}',flush=True)
            report['audio_metrics'] = worker.metrics
            report['recognized_command'] = any(m.get('text') and __import__('commands').interpret(m['text']) for m in worker.metrics)
        print(json.dumps(report,indent=2),flush=True)
    if a.output: a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__': main()
