"""One explicit bounded real-microphone test of the shared command path."""
from bootstrap import *
import argparse
import json
import time
from audio import AudioConfig
from phase9a.bus import InputBus
from phase9a.voice import VoiceInput

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',type=int,required=True);p.add_argument('--device-name',default='Realtek')
    p.add_argument('--hostapi',default='Windows WASAPI');p.add_argument('--seconds',type=float,default=6.)
    p.add_argument('--delay',type=float,default=5.);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output required')
    a.output.mkdir(parents=True);bus=InputBus();ticket=bus.open_window()
    config=AudioConfig(str(PROJECT/'phase6b/models/whisper-tiny'),a.device,a.seconds,2,.003,a.device_name,a.hostapi,0)
    worker=VoiceInput(bus,config,a.output);worker.start()
    print(f'Prueba explicita en {a.delay} s: espere ESCUCHANDO y diga Patea a la derecha',flush=True)
    time.sleep(a.delay);worker.request(ticket)
    start=time.perf_counter();messages=[]
    try:
        while time.perf_counter()-start<60:
            while (m:=bus.drain()) is not None:
                print(m.kind,m.text,'->',m.intent,flush=True);messages.append(m.__dict__)
            if worker.metrics and not worker.busy:break
            time.sleep(.05)
    finally:joined=worker.close()
    (a.output/'probe.json').write_text(json.dumps(dict(messages=messages,metrics=worker.metrics,worker_joined=joined,
        note='Real capture; correctness of spoken phrase requires human confirmation'),indent=2),encoding='utf-8')
if __name__=='__main__':main()
