"""Scoped resource adapter: real relative roots, identical checksums, no physics hooks."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=Path(__file__).with_name('external_manifest.json')
BASELINE=ROOT/'phase2/results/benchmark/single_01.json'

def dependency_record(manifest=MANIFEST,workspace=None):
    workspace=Path(workspace or ROOT.parent).resolve()
    raw=json.loads(Path(manifest).read_text(encoding='utf-8'))
    if raw['version']!=1 or not raw['files']:raise ValueError('Invalid dependency manifest')
    output={}
    for row in raw['files']:
        if row['root'] not in ('RoboNaldo_Deploy','unitree_mujoco'):raise ValueError('Unknown dependency root')
        base=workspace/row['root'];path=(base/row['path']).resolve()
        if Path(row['path']).is_absolute() or not path.is_relative_to(base.resolve()):raise ValueError('Unsafe resource path')
        if str(path) in output:raise ValueError('Duplicate dependency')
        if not path.is_file():raise FileNotFoundError(f'Missing authorized external resource: {row["root"]}/{row["path"]}')
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=row['sha256']:raise ValueError(f'Dependency checksum mismatch: {row["root"]}/{row["path"]}')
        output[str(path)]=actual
    return {'external_inputs':{'files_sha256':output}}

def install(engine,record=None):
    """Bind only a private runner's Path/HOME; pathlib and historical sources are unchanged.

    The historical runner consumes only external_inputs.files_sha256 from BASELINE.
    Supply that real, verified map in memory for this exact read, not fake file paths
    and not a fabricated historical physical result. Other reads are untouched.
    """
    payload=json.dumps(dependency_record() if record is None else record)
    NativePath=type(Path())
    class ResourcePath(NativePath):
        def read_text(self,*args,**kwargs):
            if self.resolve()==BASELINE.resolve():return payload
            return super().read_text(*args,**kwargs)
    engine.Path=ResourcePath
    engine.HOME=ResourcePath(engine.HOME)
    return engine

def components(catalog,*args,**kwargs):
    from phase8c.runtime import components as original
    Base,Selector=original(catalog,*args,**kwargs)
    class Runtime(Base):
        def __init__(self):
            record=dependency_record()  # preflight before any robot/policy initialization
            super().__init__()
            install(self.engine,record)
    return Runtime,Selector
