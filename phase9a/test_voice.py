from bootstrap import *
import threading
import time
import unittest
from types import SimpleNamespace
import numpy as np
from audio import AudioConfig
from phase9a.bus import InputBus
from phase9a.voice import VoiceInput
from phase9a.console import ConsoleInput

class FakeModel:
    def __init__(self,*a,**k):pass
    def transcribe(self,*a,**k):return [SimpleNamespace(text='Patea a la derecha.')],SimpleNamespace(duration_after_vad=1.)

class Tests(unittest.TestCase):
    def config(self):return AudioConfig(str(PROJECT/'phase6b/models/whisper-tiny'))
    def wait(self,predicate):
        end=time.perf_counter()+3
        while time.perf_counter()<end:
            if predicate():return
            time.sleep(.01)
        self.fail('worker timeout')
    def test_no_capture_without_explicit_request_and_one_request_one_capture(self):
        b=InputBus();calls=[]
        def capture(*a,**kw):calls.append(True);kw['on_ready']();return np.ones(16000,dtype=np.float32)*.02,.02
        w=VoiceInput(b,self.config(),capture_fn=capture,model_factory=FakeModel);w.start()
        try:
            time.sleep(.15);self.assertEqual(calls,[])
            ticket=b.open_window();self.assertTrue(w.request(ticket)[0]);self.wait(lambda:not w.busy)
            time.sleep(.1);self.assertEqual(len(calls),1)
            messages=[]
            while (m:=b.drain()) is not None:messages.append(m)
            result=next(m for m in messages if m.kind=='command')
            self.assertEqual(result.intent,'shot:right_inter_m080');self.assertEqual(result.ticket,ticket)
            self.assertEqual(w.metrics[0]['source'],'test_double')
        finally:self.assertTrue(w.close())
    def test_capture_error_preserves_text_bus(self):
        b=InputBus();ticket=b.open_window()
        def bad(*a,**k):raise OSError('device unavailable test')
        w=VoiceInput(b,self.config(),capture_fn=bad,model_factory=FakeModel);w.start()
        try:
            w.request(ticket);self.wait(lambda:not w.busy)
            self.assertEqual(w.metrics[0]['error'],'OSError');self.assertTrue(b.submit('Patea al centro'))
        finally:self.assertTrue(w.close())
    def test_cancellation_during_model_load_cannot_open_stream_after_selection(self):
        b=InputBus();ticket=b.open_window();load=threading.Event();release=threading.Event();calls=[]
        def factory(*a,**k):load.set();release.wait(2);return FakeModel()
        w=VoiceInput(b,self.config(),capture_fn=lambda *a,**k:calls.append(True),model_factory=factory);w.start()
        try:
            w.request(ticket);self.assertFalse(w.capture_closed.is_set());self.assertTrue(load.wait(1))
            b.close_window();w.cancel_request();release.set();self.wait(lambda:not w.busy)
            self.assertEqual(calls,[]);self.assertTrue(w.capture_closed.is_set())
        finally:release.set();self.assertTrue(w.close())
    def test_asr_result_after_window_close_is_discarded(self):
        b=InputBus();ticket=b.open_window();entered=threading.Event();release=threading.Event()
        class Slow(FakeModel):
            def transcribe(self,*a,**k):entered.set();release.wait(2);return super().transcribe(*a,**k)
        w=VoiceInput(b,self.config(),capture_fn=lambda *a,**k:(np.ones(100,dtype=np.float32),1.),model_factory=Slow);w.start()
        try:
            w.request(ticket);self.assertTrue(entered.wait(1));b.close_window();b.open_window();release.set();self.wait(lambda:not w.busy)
            while (m:=b.drain()) is not None:self.assertNotEqual(m.kind,'command')
        finally:release.set();self.assertTrue(w.close())
    def test_console_thread_can_close_without_a_line(self):
        import io
        reader=ConsoleInput(InputBus(),io.StringIO());reader.start();self.assertTrue(reader.close())

if __name__=='__main__':unittest.main()
