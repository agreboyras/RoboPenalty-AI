from bootstrap import *
import importlib.metadata
import json
from phase8c.integrity import sources

def main():
    out=HERE/'results';out.mkdir(exist_ok=True)
    if (out/'audit.json').exists():raise ValueError('Audit already exists')
    protected={p:h for p,h in sources().items() if not Path(p).is_relative_to(HERE)}
    for p in (PROJECT/'phase8c').glob('*'):
        if p.is_file():protected[str(p)]=__import__('hashlib').sha256(p.read_bytes()).hexdigest()
    (out/'protected_before.json').write_text(json.dumps(protected,indent=2),encoding='utf-8')
    packages={}
    for name in ('mujoco','numpy','faster-whisper','sounddevice','av'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    try:
        from audio import devices
        inventory=devices()
    except Exception as exc:inventory={'error':str(exc)}
    model=PROJECT/'phase6b/models/whisper-tiny'
    result=dict(packages=packages,model_path=str(model),local_model_available=(model/'model.bin').is_file(),devices=inventory,
        integration='Select inside on_prepared/selector.choose after physical reset, before first step; wait loop services native viewer and owner command queue',
        audio='Existing capture/resampler reusable; old continuous VoiceWorker must not be used for directed input',
        learning='Automatic selector unchanged; manual transactions kept outside its state',
        goalkeeper='Runtime/ObservationReader unchanged: physical ball position/velocity and own rail state only')
    (out/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
