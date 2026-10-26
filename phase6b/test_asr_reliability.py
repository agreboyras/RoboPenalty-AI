"""Offline evaluation truth/accounting and command safety; no microphone required."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from asr_profiles import decoding_options,decoding_details
from audio_trace import write_float_wav
from commands import interpret, CommandBus
from control import Control
from evaluate_asr import collect,evaluate, score_prediction, state_policy, summarize

HERE=Path(__file__).resolve().parent


class ReliabilityTests(unittest.TestCase):
    def test_profiles_preserve_current_and_change_only_named_options(self):
        current=decoding_options()
        self.assertEqual(current,dict(language='es',task='transcribe',beam_size=1,vad_filter=True,condition_on_previous_text=False))
        self.assertEqual(decoding_options('beam5'),dict(current,beam_size=5))
        self.assertIn('initial_prompt',decoding_options('prompt'))
        with self.assertRaises(ValueError):decoding_options('invented')

    def test_unknown_is_not_a_negative_label(self):
        r=score_prediction(None,'start')
        self.assertFalse(r['labelled']);self.assertIsNone(r['false_positive'])
        row=dict(configuration='tiny_current',score=r,asr_wall_s=.1,intent='start',raw_intent='start',passes_rms_gate=True)
        report=summarize([row])['tiny_current']
        self.assertEqual(report['labelled'],0);self.assertEqual(report['false_positives'],0)

    def test_explicit_labels_and_wrong_command(self):
        negative=dict(intent=None,provenance='Human confirmed no command')
        self.assertTrue(score_prediction(negative,'start')['false_positive'])
        positive=dict(intent='pause',provenance='Human confirmed pausar partido')
        wrong=score_prediction(positive,'stop')
        self.assertTrue(wrong['false_positive']);self.assertTrue(wrong['false_negative'])
        self.assertTrue(score_prediction(positive,'pause')['correct'])
        with self.assertRaises(ValueError):score_prediction({'intent':'start'},None)

    def test_no_state_is_not_acceptance(self):
        self.assertIsNone(state_policy('start',None)['accepted'])
        self.assertTrue(state_policy('start',dict(phase='READY',active=False))['accepted'])
        self.assertFalse(state_policy('start',dict(phase='SHOOTING',active=True))['accepted'])

    def test_five_commands_and_state_policy_matrix(self):
        phrases={'Iniciar partido':'start','Mostrar marcador':'score','Pausar partido':'pause',
                 'Reanudar partido':'resume','Detener partido':'stop'}
        for phase in ('READY','PREPARING','SHOOTING','RESOLVING','FINISHED'):
            for phrase,intent in phrases.items():
                with self.subTest(phase=phase,phrase=phrase):
                    self.assertEqual(interpret(phrase),intent)
                    active=phase in ('PREPARING','SHOOTING','RESOLVING')
                    context=dict(phase=phase,active=active,paused=False)
                    expected={'start':phase=='READY','score':True,'pause':active,'resume':False,'stop':True}[intent]
                    self.assertEqual(state_policy(intent,context)['accepted'],expected)
        self.assertTrue(state_policy('resume',dict(phase='SHOOTING',active=True,paused=True))['accepted'])

    def test_parser_stays_strict_including_observed_bad_transcripts(self):
        for text in ['pausa','Otro marcador','No lo salga el vídeo','iniciar partidos',
                     'no quiero iniciar partido','iniciar partido y detener partido',
                     'Comandos de un simulador de penales','Inincierto partido','pausar partido no']:
            with self.subTest(text=text):self.assertIsNone(interpret(text))

    def test_real_queue_rejects_duplicate_and_resumes_on_owner(self):
        bus=CommandBus();c=Control(bus,emit=lambda *a,**k:None)
        bus.submit('Iniciar partido','voice');bus.submit('Iniciar partido','voice');c.pump()
        self.assertEqual([e['accepted'] for e in c.events],[True,False])
        self.assertFalse(c.events[0]['state_before']['start_requested'])
        self.assertTrue(c.events[1]['state_before']['start_requested'])
        c.start_requested=False;c.active=True;c.phase='SHOOTING'
        for phrase in ['Pausar partido','Mostrar marcador','Reanudar partido','Detener partido']:
            bus.submit(phrase,'voice');c.pump();self.assertTrue(c.events[-1]['accepted'])
        self.assertFalse(c.paused);self.assertTrue(c.stop_requested)

    def test_decoding_failure_stage_without_new_confidence_gate(self):
        self.assertEqual(decoding_details([],SimpleNamespace(duration_after_vad=0),None)['recognition_stage'],'vad_no_speech')
        self.assertEqual(decoding_details([],SimpleNamespace(duration_after_vad=1),None)['recognition_stage'],'decoder_empty')
        segment=SimpleNamespace(text='Otro marcador',avg_logprob=-.5,no_speech_prob=.1)
        report=decoding_details([segment],None,None)
        self.assertEqual(report['recognition_stage'],'parser_unknown')
        self.assertEqual(report['segments'][0]['avg_logprob'],-.5)
        self.assertEqual(decoding_details([SimpleNamespace(text='iniciar partido')],None,'start')['recognition_stage'],'recognized_intent')

    def test_collection_requires_explicit_confirmation_and_includes_negatives(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            a=SimpleNamespace(output=Path(temp)/'corpus',device=15,device_name=None,device_hostapi=None,
                              seconds=.25,repetitions=1,blocksize=0)
            answers=['','n']+['','s']*6
            def fake_capture(config,stop,**kwargs):
                audio=np.ones(4000,dtype=np.float32)*.01
                kwargs['raw_sink'].update(audio=audio,rate=16000)
                return audio,.01
            with patch('builtins.input',side_effect=answers),patch('audio.resolve_input',return_value={'index':15}),patch('audio.capture',side_effect=fake_capture):
                collect(a)
            cases=json.loads((a.output/'manifest.json').read_text())['cases']
            self.assertIsNone(cases[0]['truth']);self.assertEqual(len(cases),7)
            self.assertIsNone(cases[-1]['truth']['intent'])
            self.assertTrue(cases[3]['context']['paused'])

    def test_offline_inference_consumed_and_rms_gate_preserved(self):
        calls=[];consumed=[]
        class Model:
            def __init__(self,*a,**k):calls.append(k)
            def transcribe(self,audio,**kwargs):
                def generate():
                    consumed.append(True)
                    yield SimpleNamespace(text='Iniciar partido.',start=0.,end=.1,avg_logprob=-.2,no_speech_prob=.01,compression_ratio=1.,temperature=0.)
                return generate(),SimpleNamespace(duration_after_vad=.1,transcription_options=None)
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            root=Path(temp);model=root/'model';model.mkdir();(model/'model.bin').write_bytes(b'test only')
            wav=root/'quiet.wav';write_float_wav(wav,np.zeros(1600,dtype=np.float32),16000)
            manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(cases=[dict(id='quiet',wav=str(wav),
                truth=dict(intent=None,provenance='Synthetic silence'),context=dict(phase='READY',active=False))])))
            a=SimpleNamespace(manifest=manifest,output=root/'eval',tiny_model=model,base_model=None,
                              profiles=['current'],min_rms=.003,seed=2026)
            with patch('faster_whisper.WhisperModel',Model):evaluate(a)
            row=json.loads((root/'eval/trials.jsonl').read_text())
            self.assertEqual(row['raw_intent'],'start');self.assertIsNone(row['intent'])
            self.assertFalse(row['owner_policy']['accepted']);self.assertEqual(len(consumed),1)
            self.assertTrue(calls[0]['local_files_only']);self.assertEqual(row['random_seed'],2026)


if __name__=='__main__':unittest.main()
