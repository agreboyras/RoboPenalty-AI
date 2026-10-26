"""Signal tests independent of microphone and spoken recognition accuracy."""
from pathlib import Path
import tempfile
import unittest
import wave
import numpy as np
from diagnose_audio import metrics,mono,prepare,read_wav,write_wav


class DiagnosticTests(unittest.TestCase):
    def test_pcm16_roundtrip_and_header(self):
        signal=np.linspace(-.8,.8,96000,dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            p=Path(temp)/'test.wav';write_wav(p,signal,16000)
            decoded,rate=read_wav(p)
            with wave.open(str(p),'rb') as w:
                self.assertEqual((w.getnframes(),w.getnchannels(),w.getsampwidth()),(96000,1,2))
            self.assertEqual(rate,16000);self.assertLessEqual(float(np.max(abs(decoded[:,0]-signal))),1/32768)
            with self.assertRaises(FileExistsError):write_wav(p,signal,16000)

    def test_stereo_layout(self):
        signal=np.array([[.25,-.5],[.5,-.25]],dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            p=Path(temp)/'stereo.wav';write_wav(p,signal,48000)
            decoded,rate=read_wav(p);self.assertEqual(rate,48000)
            np.testing.assert_array_equal(decoded,signal)

    def test_six_second_rate_and_pitch(self):
        for rate in (16000,44100,48000):
            with self.subTest(rate=rate):
                signal=(.2*np.sin(2*np.pi*440*np.arange(rate*6)/rate)).astype(np.float32)
                result=prepare(signal,rate)
                self.assertEqual(len(result),96000)
                peak=np.argmax(abs(np.fft.rfft(result)))*16000/len(result)
                self.assertAlmostEqual(peak,440,places=2)
                self.assertAlmostEqual(metrics(result,16000)['rms'],.2/np.sqrt(2),places=3)

    def test_mono_channel_selection_and_cancellation(self):
        signal=np.column_stack([np.ones(100,dtype=np.float32)*.1,np.ones(100,dtype=np.float32)*-.1])
        np.testing.assert_array_equal(mono(signal,'mean'),np.zeros(100))
        np.testing.assert_array_equal(mono(signal,'1'),signal[:,0])
        np.testing.assert_array_equal(mono(signal,'2'),signal[:,1])
        self.assertGreater(metrics(signal,16000)['rms'],0)

    def test_metrics_channels(self):
        r=metrics(np.array([[.5,0],[-.5,0]],dtype=np.float32),16000)
        self.assertEqual(r['channels'],2);self.assertEqual(r['frames'],2)
        self.assertEqual(r['channels_metrics'][0]['rms'],.5)
        self.assertEqual(r['channels_metrics'][1]['rms'],0)
        self.assertEqual(r['peak'],.5)

    def test_invalid_audio(self):
        for samples in (np.array([]),np.array([float('nan')])):
            with self.assertRaises(ValueError):metrics(samples,16000)
        with self.assertRaises(ValueError):mono(np.zeros(2,dtype=np.float32),'2')


if __name__=='__main__':unittest.main(verbosity=2)
