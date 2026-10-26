"""Unit tests: grammar, policy, queue epochs, thread ownership and audio isolation."""
import contextlib
import io
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
from commands import CommandBus, interpret
from control import Control
from audio import AudioConfig, VoiceWorker
from session import Service


class GrammarTests(unittest.TestCase):
    def test_required(self):
        for text, intent in [('Iniciar partido','start'),('Empezar tanda','start'),
            ('Patear cinco penales','five'),('Siguiente penal','next'),('Pausar partida','pause'),
            ('Continuar partida','resume'),('Detener partido','stop'),('Reiniciar partido','reset'),
            ('Mostrar marcador','score'),('¿Cuántos goles llevamos?','score')]:
            with self.subTest(text=text): self.assertEqual(interpret(text),intent)

    def test_variants(self):
        for text, intent in [('Por favor, iniciá el partido','start'),('reanuda la tanda por favor','resume'),
                              ('Patear 5 penales','five'),('cuántos goles tenemos','score')]:
            self.assertEqual(interpret(text),intent)

    def test_unknown_and_negations(self):
        for text in ['', 'hola', 'no iniciar partido', 'no pausar partida', 'quiero chocolate',
                     'iniciar partido y detener partido', 'reiniciar el motor', 'patear cien penales']:
            with self.subTest(text=text): self.assertIsNone(interpret(text))


class QueueTests(unittest.TestCase):
    def test_fifo(self):
        b=CommandBus();b.submit('iniciar partido');b.submit('mostrar marcador')
        self.assertEqual([b.drain().intent,b.drain().intent],['start','score']);self.assertIsNone(b.drain())

    def test_bounded(self):
        b=CommandBus(1);self.assertTrue(b.submit('hola'));self.assertFalse(b.submit('hola'));self.assertEqual(b.dropped,1)

    def test_reset_clears_pending_and_inflight_audio(self):
        b=CommandBus();old=b.epoch();b.submit('iniciar partido')
        self.assertEqual(b.rotate(),1);self.assertIsNone(b.drain())
        self.assertFalse(b.submit('iniciar partido','voice',generation=old))
        self.assertTrue(b.submit('mostrar marcador'))

    def test_thread_producer(self):
        b=CommandBus();t=threading.Thread(target=lambda:b.submit('mostrar marcador','voice'));t.start();t.join()
        self.assertEqual(b.drain().intent,'score')


class PolicyTests(unittest.TestCase):
    def setUp(self): self.bus=CommandBus();self.c=Control(self.bus,emit=lambda *a,**k:None)

    def test_duplicate_start(self):
        self.assertTrue(self.c.handle('start')[0]);self.assertFalse(self.c.handle('start')[0])

    def test_five(self):
        self.c.handle('five');self.assertTrue(self.c.five_requested)

    def test_unknown(self): self.assertFalse(self.c.handle(None)[0])

    def test_reset_states(self):
        for phase in ('PREPARING','SHOOTING','RESOLVING'):
            self.c.phase=phase;self.assertFalse(self.c.handle('reset')[0])
        for phase in ('READY','FINISHED'):
            self.c.phase=phase;self.assertTrue(self.c.handle('reset')[0])

    def test_start_active_states(self):
        for phase in ('PREPARING','SHOOTING','RESOLVING','FINISHED'):
            self.c.phase=phase;self.assertFalse(self.c.handle('start')[0])

    def test_pause_resume(self):
        self.assertFalse(self.c.handle('pause')[0]);self.c.active=True;self.c.phase='SHOOTING'
        self.assertTrue(self.c.handle('pause')[0]);self.assertFalse(self.c.handle('pause')[0])
        self.assertTrue(self.c.handle('resume')[0]);self.assertFalse(self.c.handle('resume')[0])

    def test_stop_resumes_and_defers(self):
        self.c.active=True;self.c.phase='SHOOTING';self.c.paused=True
        self.c.handle('stop');self.assertTrue(self.c.stop_requested);self.assertFalse(self.c.paused)
        self.assertEqual(self.c.phase,'SHOOTING')

    def test_next_gated(self):
        self.assertFalse(self.c.handle('next')[0]);self.c.manual_next=True;self.c.waiting_next=True
        self.assertTrue(self.c.handle('next')[0]);self.assertFalse(self.c.handle('next')[0])

    def test_next_rejects_shooting(self):
        self.c.manual_next=True;self.c.waiting_next=True;self.c.phase='SHOOTING'
        self.assertFalse(self.c.handle('next')[0])

    def test_score_in_all_states(self):
        self.c.score={'goals':3,'saves':2,'misses':0}
        for phase in ('READY','PREPARING','SHOOTING','RESOLVING','FINISHED'):
            self.c.phase=phase;ok,text=self.c.handle('score');self.assertTrue(ok);self.assertIn('Goles 3',text)

    def test_reset_drops_later_messages(self):
        self.bus.submit('reiniciar partido');self.bus.submit('iniciar partido');self.c.pump()
        self.assertTrue(self.c.reset_requested);self.assertFalse(self.c.start_requested)
        self.c.reset();self.assertEqual(self.c.score['goals'],0);self.assertEqual(self.c.phase,'READY')

    def test_wrong_thread_rejected(self):
        errors=[]
        def run():
            try:self.c.pump()
            except RuntimeError:errors.append(True)
        t=threading.Thread(target=run);t.start();t.join();self.assertEqual(errors,[True])


class BoundaryTests(unittest.TestCase):
    def test_render_thread_join_on_close(self):
        from session import CommandPresenter, Presenter
        class Render:
            done=False
            def join(self,timeout):self.done=True
            def is_alive(self):return not self.done
        p=CommandPresenter.__new__(CommandPresenter);p.handle=object();p.render_threads=[Render()]
        with patch.object(Presenter,'close'):p.close()
        self.assertTrue(p.render_joined)

    def test_score_current_during_result_presentation(self):
        from session import CommandMatch, VisualMatch
        from game import Phase, Scoreboard, PenaltyState
        b=CommandBus();c=Control(b,emit=lambda *a,**k:None)
        m=CommandMatch.__new__(CommandMatch)
        m.service=SimpleNamespace(control=c,checkpoint=lambda:None)
        m.score=Scoreboard(goals=1);m.phase=Phase.RESOLVING;m.current=PenaltyState(1)
        seen=[]
        def transition(phase):
            seen.append(c.handle('score')[1]);m.phase=phase
        with patch.object(VisualMatch,'transition',side_effect=transition):m.transition(Phase.FINISHED)
        self.assertIn('Goles 1',seen[0])

    def test_true_pause_keeps_state_and_adjusts_pacing(self):
        import numpy as np
        b=CommandBus();c=Control(b,emit=lambda *a,**k:None);c.active=True;c.phase='SHOOTING'
        state=np.array([1.,2.,3.]);data=SimpleNamespace(time=.6)
        r=SimpleNamespace(data=data,integration_state=lambda d:state.copy(),engine=SimpleNamespace(np=np))
        p=SimpleNamespace(sync=lambda kind:None,episode_start=10.)
        s=Service(c,r,p);b.submit('pausar partida')
        t=threading.Thread(target=lambda:(time.sleep(.08),b.submit('continuar partida')));t.start()
        s.checkpoint();t.join()
        self.assertTrue(s.pause_records[0]['full_integration_state_unchanged'])
        self.assertEqual(s.pause_records[0]['sim_after_s'],.6);self.assertGreater(p.episode_start,10.05)


class AudioTests(unittest.TestCase):
    def test_console_fallback(self):
        from audio import text_worker
        b=CommandBus()
        with patch('builtins.input',side_effect=['iniciar partido','mostrar marcador',EOFError()]):
            thread=text_worker(b);thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual([b.drain().intent,b.drain().intent],['start','score'])

    def test_native_resampling(self):
        import numpy as np
        from audio import resample
        original=np.sin(2*np.pi*440*np.arange(48000)/48000).astype(np.float32)
        result=resample(original,48000)
        self.assertEqual(len(result),16000);self.assertEqual(result.dtype,np.float32)
        self.assertGreater(float(np.sqrt(np.mean(result*result))),.69)

    def test_config_validation(self):
        for seconds in (0,-1,float('nan'),31):
            with self.assertRaises(ValueError):AudioConfig(listen_s=seconds)

    def test_worker_only_enqueues_and_is_nonblocking(self):
        import numpy as np
        b=CommandBus();c=Control(b,emit=lambda *a,**k:None)
        entered=threading.Event();release=threading.Event();calls=[]
        class Model:
            def __init__(self,*args,**kwargs): calls.append(kwargs)
            def transcribe(self,*args,**kwargs):
                entered.set();release.wait(2)
                return [SimpleNamespace(text='Iniciar partido')],None
        w=VoiceWorker(b,AudioConfig('test'),once=True)
        with patch('faster_whisper.WhisperModel',Model),patch('audio.capture',return_value=(np.ones(1600),.1)):
            w.start();self.assertTrue(entered.wait(2))
            start=time.perf_counter();b.submit('mostrar marcador');c.pump()
            self.assertLess(time.perf_counter()-start,.1)
            self.assertFalse(c.start_requested) # ASR unfinished, owner still responsive
            release.set();w.thread.join(2);self.assertFalse(w.thread.is_alive())
            self.assertFalse(c.start_requested) # audio worker has not changed game state
            c.pump();self.assertTrue(c.start_requested)
        self.assertTrue(calls[0]['local_files_only']);self.assertEqual(calls[0]['device'],'cpu')

    def test_device_failure_is_reported(self):
        b=CommandBus();w=VoiceWorker(b,AudioConfig('test'),once=True)
        with patch('faster_whisper.WhisperModel'),patch('audio.capture',side_effect=RuntimeError('device gone')):
            w.start();w.thread.join(2)
        self.assertEqual(w.metrics[-1]['error'],'RuntimeError')
        self.assertIn('device gone',w.metrics[-1]['message'])


if __name__=='__main__':unittest.main(verbosity=2)
