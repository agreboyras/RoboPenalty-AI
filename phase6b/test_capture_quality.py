"""Quality instrumentation/probe tests, not acoustic or Bluetooth validation."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
from audio import AudioConfig,capture,resolve_input
from audio_quality import signal_report,analyze
from audio_trace import write_float_wav
from capture_compare import held_takes,session_take
from test_live_audio import FakeSoundDevice

HERE=Path(__file__).resolve().parent


class CaptureQualityTests(unittest.TestCase):
    def test_host_blocksize_and_read_timing(self):
        sd=FakeSoundDevice();meta={'record_read_timing':True}
        with patch.dict('sys.modules',{'sounddevice':sd}):
            samples,_=capture(AudioConfig(device=15,listen_s=.25,stream_blocksize=0),threading.Event(),metadata=meta)
        self.assertEqual(sd.open_calls[0]['blocksize'],0);self.assertEqual(len(samples),4000)
        self.assertEqual([r['returned_frames'] for r in meta['reads']],[1600,1600,800])
        self.assertEqual(meta['stream_blocksize_frames'],0)
        self.assertFalse(any(r['overflow'] for r in meta['reads']))

    def test_negative_blocksize(self):
        with self.assertRaises(ValueError):AudioConfig(stream_blocksize=-1)

    def test_held_stream_opens_once_drains_gaps_and_saves_after_close(self):
        sd=FakeSoundDevice();config=AudioConfig(device=15,listen_s=.25,stream_blocksize=0)
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp,patch.dict('sys.modules',{'sounddevice':sd}):
            rows=held_takes(config,Path(temp),resolve_input(config),2,.1)
            self.assertTrue(sd.closed);self.assertEqual(len(sd.open_calls),1)
            self.assertEqual(rows[1]['start_frame_in_continuous_stream'],5600)
            self.assertEqual(rows[1]['gap_drained_s'],.1)
            self.assertEqual(len(rows[0]['reads']),3)
            self.assertTrue((Path(temp)/'take_02/capture_000001_native.wav').is_file())

    def test_session_probe_has_no_asr_and_preserves_frames(self):
        sd=FakeSoundDevice();config=AudioConfig(device=15,listen_s=.25)
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp,patch.dict('sys.modules',{'sounddevice':sd}):
            result=session_take(config,Path(temp)/'take',resolve_input(config))
        self.assertFalse(result['transcribed']);self.assertEqual(len(result['reads']),3)

    def test_zero_runs_and_boundary_outlier_are_measurements_not_loss_verdict(self):
        a=np.ones(16000,dtype=np.float32)*.1;a[3200:4800]=0
        result=signal_report(a,16000,[3200,4800])
        self.assertEqual(result['channels'][0]['exact_zero_runs_at_least_5ms'],[{'start_s':.2,'duration_s':.1}])
        self.assertEqual(len(result['channels'][0]['boundaries_above_global_p999_s']),2)
        self.assertNotIn('packet_loss',result)

    def test_native_whisper_and_independent_decode_comparison(self):
        a=(np.arange(1600,dtype=np.float32)%100-50)/32768
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            folder=Path(temp);p=folder/'native.wav';q=folder/'asr.wav'
            digest=write_float_wav(p,a,16000);write_float_wav(q,a,16000)
            result=analyze(p,{'asr_array_sha256':digest},q,folder,True)
            self.assertTrue(result['whisper_comparison']['array_equal_after_expected_conversion'])
            self.assertTrue(result['independent_pyav_decode_equal']);self.assertTrue(result['playback_copy']['sample_equal'])


if __name__=='__main__':unittest.main(verbosity=2)
