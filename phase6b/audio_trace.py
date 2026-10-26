"""Opt-in forensic traces; this module has no simulation references."""
import hashlib
import json
from pathlib import Path
import struct


def summarize_metrics(metrics,events,joined):
    """Merge owner decisions into the final report without touching worker state."""
    decisions={e['capture_id']:{k:e[k] for k in ('accepted','reason','phase','generation')}
               for e in events if e.get('capture_id')}
    result=[]
    for entry in metrics:
        entry=dict(entry)
        if entry.get('capture_id') in decisions:entry['decision']=decisions[entry['capture_id']]
        elif joined and entry.get('decision',{}).get('reason')=='pending_owner':
            entry['decision']={'accepted':False,'reason':'not_processed_before_reset_or_shutdown'}
        result.append(entry)
    return result


def read_float_wav(path):
    """Read our RIFF IEEE_FLOAT32 files without quantizing or changing channels."""
    import numpy as np
    raw=Path(path).read_bytes()
    if len(raw)<12 or raw[:4]!=b'RIFF' or raw[8:12]!=b'WAVE' or struct.unpack_from('<I',raw,4)[0]+8!=len(raw):
        raise ValueError('Invalid/truncated RIFF WAV')
    offset=12;fmt=None;payload=None
    while offset+8<=len(raw):
        kind=raw[offset:offset+4];size=struct.unpack_from('<I',raw,offset+4)[0]
        offset+=8
        if offset+size>len(raw):raise ValueError('Truncated WAV chunk')
        if kind==b'fmt ':fmt=raw[offset:offset+size]
        if kind==b'data':payload=raw[offset:offset+size]
        offset+=size+(size%2)
    if fmt is None or len(fmt)<16 or payload is None:raise ValueError('Missing WAV format/data')
    tag,channels,rate,_,align,bits=struct.unpack_from('<HHIIHH',fmt)
    if tag!=3 or bits!=32 or channels<1 or rate<1 or align!=channels*4 or len(payload)%align:
        raise ValueError('Expected IEEE_FLOAT32 WAV')
    samples=np.frombuffer(payload,dtype='<f4').reshape(-1,channels).copy()
    if not samples.size or not np.isfinite(samples).all():raise ValueError('Invalid WAV samples')
    return samples,rate


def write_float_wav(path, samples, rate):
    """IEEE float32 WAV preserves the exact ndarray passed to Whisper (no gain/PCM quantization)."""
    import numpy as np
    data = np.asarray(samples,dtype='<f4')
    if data.ndim == 1: data = data[:,None]
    if data.ndim != 2 or not data.size or not np.isfinite(data).all():
        raise ValueError('Nonempty finite audio required')
    channels = data.shape[1]
    payload = np.ascontiguousarray(data).tobytes()
    fmt = struct.pack('<HHIIHHH',3,channels,rate,rate*channels*4,channels*4,32,0)
    chunks = b'fmt '+struct.pack('<I',len(fmt))+fmt
    chunks += b'fact'+struct.pack('<II',4,len(data))
    chunks += b'data'+struct.pack('<I',len(payload))+payload
    with Path(path).open('xb') as f:
        f.write(b'RIFF'+struct.pack('<I',4+len(chunks))+b'WAVE'+chunks)
    return hashlib.sha256(payload).hexdigest()


class AudioTrace:
    def __init__(self,directory):
        self.directory = Path(directory).resolve()
        allowed = Path(__file__).resolve().parent/'results'
        if not self.directory.is_relative_to(allowed):
            raise ValueError('Audio diagnostics must be inside phase6b/results')
        self.directory.mkdir(parents=True,exist_ok=False)

    def path(self,capture_id):
        if not capture_id.startswith('capture_') or not capture_id[8:].isdigit():
            raise ValueError('Invalid capture ID')
        return self.directory/f'{capture_id}.json'

    def begin(self,capture_id,record,native,rate,audio):
        native_path=self.directory/f'{capture_id}_native.wav'
        whisper_path=self.directory/f'{capture_id}_whisper.wav'
        write_float_wav(native_path,native,rate)
        digest=write_float_wav(whisper_path,audio,16000)
        record.update(native_wav=str(native_path),whisper_wav=str(whisper_path),
                      asr_array_sha256=digest,wav_format='IEEE_FLOAT32, exact samples; no normalization')
        self.save(capture_id,record)

    def save(self,capture_id,record):
        self.path(capture_id).write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')

    def decision(self,event):
        # Called exclusively on the command owner thread, AFTER the producer has
        # persisted the completed capture record and enqueued its ID.
        capture_id=event.get('capture_id')
        if not capture_id:return
        path=self.path(capture_id)
        record=json.loads(path.read_text(encoding='utf-8'))
        record['decision']={k:event[k] for k in ('accepted','reason','phase','generation')}
        if 'state_before' in event:record['decision']['state_before']=event['state_before']
        self.save(capture_id,record)

    def finalize(self):
        for path in self.directory.glob('capture_*.json'):
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('decision',{}).get('reason')=='pending_owner':
                record['decision']={'accepted':False,'reason':'not_processed_before_reset_or_shutdown'}
                path.write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
