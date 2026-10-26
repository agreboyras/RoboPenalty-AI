"""Diagnostic annotations must preserve unknown labels and original files."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from diagnose_audio import HERE
from label_pause import annotate
from prepare_pause_review import eligible


class PauseReviewTests(unittest.TestCase):
    def test_listening_labels_do_not_infer_intent_or_change_source(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            root=Path(temp);wav=root/'copy.wav';wav.touch()
            review=root/'review.json';review.write_text(json.dumps(dict(session='synthetic fixture',captures=[
                dict(capture_id=f'capture_{n:06d}',number=n,playback_wav=str(wav),metrics=dict(duration_s=6),source_native_sha256='synthetic')
                for n in (26,27)])),encoding='utf-8')
            original=review.read_bytes()
            with patch('winsound.PlaySound') as play,patch('builtins.input',side_effect=['Pausar partido','c','','i']):
                output=annotate(review,[26,27])
            rows=json.loads(output.read_text(encoding='utf-8'))['annotations']
            self.assertEqual(rows[0]['human_transcript'],'Pausar partido');self.assertIsNone(rows[0]['intent'])
            self.assertIsNone(rows[1]['human_transcript']);self.assertIsNone(rows[1]['intent'])
            self.assertEqual(play.call_count,2);self.assertEqual(review.read_bytes(),original)

    def test_missing_capture_is_rejected_before_playback(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            p=Path(temp)/'review.json';p.write_text(json.dumps(dict(captures=[])))
            with self.assertRaises(ValueError):annotate(p,[99])

    def test_latest_session_filter_needs_diagnostics_and_actual_host_block(self):
        with tempfile.TemporaryDirectory(dir=HERE/'results') as temp:
            root=Path(temp);audio=root/'audio';audio.mkdir();p=root/'session.json'
            p.write_text(json.dumps(dict(voice_enabled=True,audio_diagnostics=str(audio))))
            meta=audio/'capture_000001.json';meta.write_text(json.dumps(dict(stream_blocksize_frames=1600)))
            self.assertIsNone(eligible(p))
            meta.write_text(json.dumps(dict(stream_blocksize_frames=0)))
            self.assertIsNotNone(eligible(p))
            p.write_text(json.dumps(dict(voice_enabled=False,audio_diagnostics=str(audio))))
            self.assertIsNone(eligible(p))


if __name__=='__main__':unittest.main()
