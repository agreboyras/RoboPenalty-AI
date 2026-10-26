"""Controlled stream/decoder tests; no synthetic test is acoustic validation."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from audio import AudioConfig,VoiceWorker,capture,resolve_input
from audio_trace import AudioTrace,write_float_wav,summarize_metrics
from commands import CommandBus,interpret
from control import Control
from diagnose_audio import read_wav,prepare

HERE=Path(__file__).resolve().parent


class FakeSoundDevice:
    class PortAudioError(Exception):pass

    def __init__(self):
        speaker={'name':'Speakers 2 (Realtek HD Audio output with HAP)','hostapi':0,
                 'max_input_channels':0,'default_samplerate':48000.}
        self.inventory=[dict(speaker) for _ in range(16)]
        self.inventory[15]={'name':'Headset (Carrello T8 Pro)','hostapi':0,
                            'max_input_channels':1,'default_samplerate':48000.}
        self.default=SimpleNamespace(device=[15,0])
        self.opened=False;self.closed=False;self.open_calls=[];self.checks=[]
        self.unsupported_16k=False;self.wrong_stream=False;self.delay=0.;self.overflow=False

    def query_devices(self):return self.inventory
    def query_hostapis(self,index):return {'name':'Windows WASAPI'}
    def check_input_settings(self,**kwargs):
        self.checks.append(kwargs)
        if self.unsupported_16k and kwargs['samplerate']==16000:raise self.PortAudioError('rate unsupported')

    def InputStream(self,**kwargs):
        self.open_calls.append(kwargs)
        sd=self
        class Stream:
            device=kwargs['device'] if not sd.wrong_stream else 0
            channels=kwargs['channels'];samplerate=kwargs['samplerate'];offset=0
            def __enter__(self):sd.opened=True;return self
            def __exit__(self,*exc):sd.closed=True;sd.opened=False
            def read(self,count):
                if sd.delay:time.sleep(sd.delay)
                t=(np.arange(count)+self.offset)/self.samplerate;self.offset+=count
                return (.025*np.sin(2*np.pi*440*t)).astype(np.float32)[:,None],sd.overflow
        return Stream()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.sd=FakeSoundDevice()
        self.patch=patch.dict('sys.modules',{'sounddevice':self.sd});self.patch.start()
    def tearDown(self):self.patch.stop()

    def test_selected_index_name_and_api(self):
        d=resolve_input(AudioConfig(device=15,device_name='Carrello T8 Pro',device_hostapi='Windows WASAPI'))
        self.assertEqual(d['index'],15);self.assertIn('Carrello',d['name'])

    def test_output_index_rejected_without_opening(self):
        with self.assertRaisesRegex(ValueError,'OUTPUT'):
            resolve_input(AudioConfig(device=0))
        self.assertFalse(self.sd.open_calls)

    def test_missing_device_and_wrong_name_api(self):
        for c in [AudioConfig(device=99),AudioConfig(device=15,device_name='Realtek'),
                  AudioConfig(device=15,device_hostapi='MME')]:
            with self.subTest(config=c),self.assertRaises(ValueError):resolve_input(c)

    def test_identity_change_rejected(self):
        c=AudioConfig(device=15);expected=resolve_input(c)
        self.sd.inventory[15]['name']='Other microphone'
        with self.assertRaisesRegex(ValueError,'identity changed'):
            capture(c,threading.Event(),expected_device=expected)
        self.assertFalse(self.sd.open_calls)

    def test_ready_only_after_open_exact_duration_and_metadata(self):
        calls=[];meta={};raw={}
        a,rms=capture(AudioConfig(device=15,listen_s=.25),threading.Event(),
                      on_ready=lambda:calls.append(self.sd.opened),metadata=meta,raw_sink=raw)
        self.assertEqual(calls,[True]);self.assertTrue(self.sd.closed)
        self.assertEqual(len(a),4000);self.assertGreater(rms,.003)
        self.assertEqual(meta['device']['index'],15);self.assertEqual(meta['native_channels'],1)
        self.assertEqual(self.sd.open_calls[0]['device'],15)
        np.testing.assert_array_equal(a,raw['audio'])

    def test_rate_fallback_preserves_device_and_samples(self):
        self.sd.unsupported_16k=True;meta={}
        a,_=capture(AudioConfig(device=15,listen_s=.25),threading.Event(),metadata=meta)
        self.assertEqual(len(a),4000);self.assertEqual(meta['native_sample_rate_hz'],48000)
        self.assertTrue(all(c['device']==15 for c in self.sd.checks))

    def test_stream_mismatch_and_overflow(self):
        self.sd.wrong_stream=True
        with self.assertRaisesRegex(RuntimeError,'differs'):capture(AudioConfig(device=15),threading.Event())
        self.sd.wrong_stream=False;self.sd.overflow=True
        with self.assertRaisesRegex(RuntimeError,'overflow'):capture(AudioConfig(device=15),threading.Event())

    def test_close_cancels_real_capture_loop_and_context(self):
        self.sd.delay=.01;ready=threading.Event();stop=threading.Event()
        t=threading.Thread(target=lambda:capture(AudioConfig(device=15,listen_s=30),stop,on_ready=ready.set))
        t.start();self.assertTrue(ready.wait(1));stop.set();t.join(1)
        self.assertFalse(t.is_alive());self.assertTrue(self.sd.closed)


class TraceTests(unittest.TestCase):
    def test_final_report_uses_owner_decision_without_mutating_worker(self):
        m=[{'capture_id':'capture_000001','decision':{'accepted':None,'reason':'pending_owner'}}]
        events=[{'capture_id':'capture_000001','accepted':True,'reason':'Inicio solicitado','phase':'READY','generation':0}]
        final=summarize_metrics(m,events,True)
        self.assertTrue(final[0]['decision']['accepted']);self.assertIsNone(m[0]['decision']['accepted'])
        self.assertFalse(summarize_metrics(m,[],True)[0]['decision']['accepted'])
        self.assertEqual(summarize_metrics(m,[],False)[0]['decision']['reason'],'pending_owner')

    def test_float_wav_replay_is_bit_exact(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            p=Path(temp)/'exact.wav'
            a=np.random.default_rng(2026).normal(0,.02,96000).astype(np.float32)
            digest=write_float_wav(p,a,16000);read,rate=read_wav(p)
            self.assertEqual(rate,16000)
            np.testing.assert_array_equal(prepare(read,rate),a)
            self.assertEqual(digest,hashlib.sha256(prepare(read,rate).tobytes()).hexdigest())

    def test_capture_transcript_owner_decision_and_offline_replay(self):
        sd=FakeSoundDevice();inputs=[]
        class Model:
            def __init__(self,*a,**k):pass
            def transcribe(self,audio,**kwargs):
                inputs.append(audio.copy())
                return [SimpleNamespace(text='iniciar partido.')],SimpleNamespace(duration_after_vad=.25,transcription_options=None)
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            trace=AudioTrace(Path(temp)/'audio');b=CommandBus()
            c=Control(b,emit=lambda *a,**k:None);c.on_command_result=trace.decision
            with patch.dict('sys.modules',{'sounddevice':sd}),patch('faster_whisper.WhisperModel',Model):
                w=VoiceWorker(b,AudioConfig('test',15,.25),once=True,trace=trace)
                w.start();w.thread.join(2);self.assertFalse(w.thread.is_alive())
            self.assertFalse(c.start_requested) # only owner can execute
            before=json.loads(trace.path('capture_000001').read_text())
            self.assertEqual(before['decision']['reason'],'pending_owner')
            saved,rate=read_wav(before['whisper_wav']);np.testing.assert_array_equal(saved[:,0],inputs[0])
            c.pump();after=json.loads(trace.path('capture_000001').read_text())
            self.assertTrue(c.start_requested);self.assertTrue(after['decision']['accepted'])
            self.assertEqual(after['intent'],'start');self.assertEqual(after['device']['index'],15)
            self.assertTrue(w.close())

    def test_trace_off_writes_no_audio(self):
        sd=FakeSoundDevice()
        with patch.dict('sys.modules',{'sounddevice':sd}),patch('faster_whisper.WhisperModel'),patch('audio_trace.write_float_wav') as write:
            w=VoiceWorker(CommandBus(),AudioConfig('test',15,.25,min_rms=1.),once=True)
            w.start();w.thread.join(2);self.assertFalse(w.thread.is_alive());write.assert_not_called()

    def test_unprocessed_command_finalization(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            t=AudioTrace(Path(temp)/'audio')
            t.save('capture_000001',{'decision':{'accepted':None,'reason':'pending_owner'}});t.finalize()
            r=json.loads(t.path('capture_000001').read_text())
            self.assertFalse(r['decision']['accepted']);self.assertIn('not_processed',r['decision']['reason'])


class IntentTests(unittest.TestCase):
    def test_exact_commands_case_accents_punctuation(self):
        for text,intent in [('Iniciar partido','start'),('Mostrar marcador','score'),('Pausar partido','pause'),
                            ('Reanudar partido','resume'),('Detener partido','stop')]:
            for phrase in (text,text.upper()+'.','¿'+text+'?',text.replace('partido','partído')):
                with self.subTest(phrase=phrase):self.assertEqual(interpret(phrase),intent)

    def test_ambiguous_asr_errors_remain_rejected(self):
        for phrase in ['Inesar Partido.','en sus partidos.','¡Inisero a partir!','en el ser partido.',
                       'no iniciar partido','no detener partido','ruido iniciar partido ruido']:
            self.assertIsNone(interpret(phrase))


if __name__=='__main__':unittest.main(verbosity=2)
