import json
from pathlib import Path
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
from portability.resources import BASELINE,dependency_record,install

class Tests(unittest.TestCase):
    def fixture(self,root):
        external=root/'RoboNaldo_Deploy';external.mkdir();p=external/'sample.txt';p.write_bytes(b'original')
        manifest=root/'manifest.json';row=dict(root='RoboNaldo_Deploy',path='sample.txt',sha256=hashlib.sha256(b'original').hexdigest())
        manifest.write_text(json.dumps(dict(version=1,files=[row])))
        return p,manifest,row
    def test_relative_roots_and_strict_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,m,row=self.fixture(root)
            self.assertEqual(dependency_record(m,root)['external_inputs']['files_sha256'],{str(p.resolve()):row['sha256']})
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):dependency_record(m,root)
    def test_traversal_and_missing_resource_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,m,row=self.fixture(root);p.unlink()
            with self.assertRaises(FileNotFoundError):dependency_record(m,root)
            row['path']='../escape';m.write_text(json.dumps(dict(version=1,files=[row])))
            with self.assertRaisesRegex(ValueError,'Unsafe'):dependency_record(m,root)
    def test_scoped_read_does_not_change_pathlib_or_original(self):
        record={'external_inputs':{'files_sha256':{'synthetic-fixture':'digest'}}}
        e=SimpleNamespace(Path=Path,HOME=BASELINE.parents[3]/'phase4a')
        original=BASELINE.read_bytes() if BASELINE.exists() else None
        install(e,record)
        self.assertEqual(json.loads(e.Path(BASELINE).read_text()),record)
        self.assertIsNot(e.Path,Path)
        if original is not None:self.assertEqual(BASELINE.read_bytes(),original)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ordinary';p.write_text('unchanged')
            self.assertEqual(e.Path(p).read_text(),'unchanged')
    def test_public_manifest_contains_only_relative_identifiers(self):
        m=json.loads(Path(__file__).with_name('external_manifest.json').read_text())
        self.assertEqual(len(m['files']),209)
        for row in m['files']:
            self.assertNotIn(':',row['path']);self.assertFalse(Path(row['path']).is_absolute())
            self.assertEqual(len(row['sha256']),64)
if __name__=='__main__':unittest.main()
