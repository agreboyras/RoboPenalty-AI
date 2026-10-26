"""Explicit one-shot jobs; audio/ASR thread sees a ticket, never MuJoCo or agents."""
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np
from audio import capture,resolve_input
from phase9a.commands import interpret,normalize

class VoiceInput:
    def __init__(self,bus,config,output=None,*,capture_fn=capture,model_factory=None):
        self.bus,self.config,self.output=bus,config,Path(output) if output else None
        self.capture_fn,self.model_factory=capture_fn,model_factory
        self.jobs=queue.Queue(1);self.stop=threading.Event();self.cancel=threading.Event();self.capture_closed=threading.Event();self.capture_closed.set()
        self.lock=threading.Lock();self.busy=False;self.metrics=[];self.model=None
        self.thread=threading.Thread(target=self.run,name='phase9a-local-asr',daemon=False)
    def status(self,text):self.bus.submit(text,'audio',kind='status')
    def request(self,ticket):
        if ticket is None:return False,'No se espera una orden de tiro'
        with self.lock:
            if self.busy:return False,'Microfono/ASR ocupado; puede usar texto'
            self.busy=True;self.cancel.clear();self.capture_closed.clear();self.jobs.put_nowait((ticket,self.bus.epoch()))
        return True,'Captura solicitada; espere ESCUCHANDO'
    def cancel_request(self):self.cancel.set()
    def start(self):self.thread.start()
    def valid(self,ticket):return not self.stop.is_set() and not self.cancel.is_set() and self.bus.active_ticket()==ticket
    def run(self):
        while not self.stop.is_set():
            try:ticket,generation=self.jobs.get(timeout=.1)
            except queue.Empty:continue
            record=dict(ticket=ticket,source='real_microphone' if self.capture_fn is capture else 'test_double',text='',intent=None)
            try:
                if not self.valid(ticket):record['stage']='cancelled_before_capture';continue
                if self.model is None:
                    if not Path(self.config.model).is_dir():raise ValueError('Modelo local no disponible; no se permiten descargas')
                    self.status('Cargando Whisper local CPU/int8; microfono cerrado')
                    factory=self.model_factory
                    if factory is None:
                        from faster_whisper import WhisperModel
                        factory=WhisperModel
                    self.model=factory(self.config.model,device='cpu',compute_type='int8',cpu_threads=self.config.cpu_threads,num_workers=1,local_files_only=True)
                if not self.valid(ticket):record['stage']='cancelled_before_capture';continue
                expected=resolve_input(self.config) if self.capture_fn is capture else None
                if not self.valid(ticket):record['stage']='cancelled_before_capture';continue
                metadata={};raw={};self.capture_closed.clear()
                start=time.perf_counter()
                try:
                    samples,rms=self.capture_fn(self.config,self.cancel,metadata=metadata,raw_sink=raw,expected_device=expected,
                        on_ready=lambda:self.status('ESCUCHANDO: diga una sola orden de tiro en espanol'))
                finally:self.capture_closed.set()
                record.update(metadata,capture_wall_s=time.perf_counter()-start,rms=rms,samples=len(samples))
                if not self.valid(ticket):record['cancelled']=True;continue
                if rms<self.config.min_rms:
                    record['stage']='below_rms_threshold'
                    self.status('Silencio/audio bajo; sin orden. Use texto o active otra captura.');continue
                self.status('TRANSCRIBIENDO; microfono cerrado')
                start=time.perf_counter()
                segments,info=self.model.transcribe(samples,language='es',task='transcribe',beam_size=1,vad_filter=True,condition_on_previous_text=False)
                text=' '.join(s.text.strip() for s in segments).strip()
                record.update(text=text,normalized=normalize(text),intent=interpret(text),asr_wall_s=time.perf_counter()-start,
                    duration_after_vad_s=getattr(info,'duration_after_vad',None),stage='decoded' if text else 'empty_transcription')
                if self.valid(ticket):self.bus.submit(text,'voice',generation=generation,ticket=ticket)
                else:record['cancelled_after_asr']=True
            except Exception as exc:
                record.update(error=type(exc).__name__,message=str(exc));self.status(f'ERROR VOZ: {exc}. Texto disponible; no se eligio un tiro.')
            finally:
                self.capture_closed.set();self.metrics.append(record)
                if self.output:
                    self.output.mkdir(parents=True,exist_ok=True)
                    (self.output/'voice_metrics.json').write_text(json.dumps(self.metrics,indent=2),encoding='utf-8')
                with self.lock:self.busy=False
    def close(self):
        self.stop.set();self.cancel.set()
        if self.thread.ident:self.thread.join(timeout=10.)
        joined=not self.thread.is_alive()
        if joined:self.capture_closed.set();self.model=None
        return joined
