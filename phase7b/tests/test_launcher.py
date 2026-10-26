from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]

class LauncherTests(unittest.TestCase):
    def invoke(self,*args):
        return subprocess.run([sys.executable,'-B',str(HERE/'run_session.py'),*args],
                              capture_output=True,text=True,encoding='utf-8')
    def test_original_distance_rejected_before_runtime_or_output(self):
        with tempfile.TemporaryDirectory(dir=HERE/'tests') as temp:
            out=Path(temp)/'output'
            result=self.invoke('--distance','original','--output',str(out))
            self.assertEqual(result.returncode,2)
            self.assertFalse(out.exists())
    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=HERE/'tests') as temp:
            sentinel=Path(temp)/'protected_sources.json'
            sentinel.write_text('sentinel',encoding='utf-8')
            result=self.invoke('--output',temp)
            self.assertEqual(result.returncode,2)
            self.assertEqual(sentinel.read_text(encoding='utf-8'),'sentinel')
    def test_output_outside_phase7b_rejected(self):
        result=self.invoke('--output',str(HERE.parent/'phase6a/not_created_by_phase7b'))
        self.assertEqual(result.returncode,2)
    def test_help_documents_visual_and_inherited_controls(self):
        result=self.invoke('--help')
        self.assertEqual(result.returncode,0,result.stderr)
        for flag in ('--camera','--no-decoration','--autostart','--manual-next','--viewer'):
            self.assertIn(flag,result.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
