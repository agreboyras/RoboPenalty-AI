"""Prepare nondestructive listening copies and the original VAD selection, without ASR."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from audio_quality import analyze
from diagnose_audio import HERE,new_directory,prepare,read_wav,write_wav


def eligible(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    if not data.get('voice_enabled') or not data.get('audio_diagnostics'):return None
    records=[json.loads(f.read_text(encoding='utf-8')) for f in (path.parent/'audio').glob('capture_*.json')]
    if not records or any(r.get('stream_blocksize_frames')!=0 for r in records):return None
    return data,records


def prepare_review(output,session_path=None):
    if session_path is None:
        candidates=sorted((HERE/'results').rglob('session.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        session_path=next((p for p in candidates if eligible(p)),None)
    if session_path is None:raise ValueError('No voice session with saved diagnostics and measured blocksize=0 found')
    session_path=Path(session_path).resolve()
    if not session_path.is_relative_to(HERE/'results'):raise ValueError('Source must be inside phase6b/results')
    selected=eligible(session_path)
    if selected is None:raise ValueError('Session must have saved voice diagnostics with blocksize=0')
    session,records=selected
    start_ids=[e['capture_id'] for e in session['commands'] if e.get('accepted') and
               e.get('intent') in ('start','five') and e.get('capture_id')]
    start_index=min(int(c.split('_')[1]) for c in start_ids) if start_ids else 0
    records=[r for r in records if int(r['capture_id'].split('_')[1])>start_index]
    records.sort(key=lambda r:(0 if r.get('transcribed') and r.get('text') else
                              1 if r.get('transcribed') else 2,int(r['capture_id'].split('_')[1])))
    events={e['capture_id']:e for e in session['commands'] if e.get('capture_id')}
    root=new_directory(output);rows=[]
    from faster_whisper.vad import VadOptions,get_speech_timestamps
    for record in records:
        cid=record['capture_id'];folder=root/cid;folder.mkdir()
        native=session_path.parent/'audio'/f'{cid}_native.wav'
        whisper=session_path.parent/'audio'/f'{cid}_whisper.wav'
        report=analyze(native,record,whisper,folder,export_pcm16=True)
        samples,rate=read_wav(whisper);audio=prepare(samples,rate)
        intervals=get_speech_timestamps(audio,VadOptions(),sampling_rate=16000)
        kept=np.concatenate([audio[s['start']:s['end']] for s in intervals]) if intervals else np.zeros(0,dtype=np.float32)
        vad_wav=folder/'vad_kept_pcm16.wav'
        if len(kept):write_wav(vad_wav,kept,16000)
        retained=len(kept)/16000;logged=record.get('duration_after_vad_s')
        source_meta=session_path.parent/'audio'/f'{cid}.json'
        row=dict(capture_id=cid,number=int(cid.split('_')[1]),
            source_native=str(native),source_native_sha256=report['file_sha256'],
            source_whisper=str(whisper),source_whisper_sha256=hashlib.sha256(whisper.read_bytes()).hexdigest(),
            source_metadata_sha256=hashlib.sha256(source_meta.read_bytes()).hexdigest(),
            playback_wav=str(folder/'listen_pcm16.wav'),vad_playback_wav=str(vad_wav) if len(kept) else None,
            playback_sample_equal=report['playback_copy']['sample_equal'],
            native_whisper_sample_equal=report['whisper_comparison']['array_equal_after_expected_conversion'],
            metrics=report['metrics'],reads=report.get('reads'),
            clipped_fraction=record.get('native_clipped_fraction'),
            original_text=record.get('text'),original_intent=record.get('intent'),
            original_decision=record.get('decision'),owner_phase=events.get(cid,{}).get('phase'),
            transcribed=record.get('transcribed'),logged_vad_kept_s=logged,recomputed_vad_kept_s=retained,
            vad_duration_matches_logged=abs(logged-retained)<1/16000 if logged is not None else None,
            vad_intervals_s=[dict(start=s['start']/16000,end=s['end']/16000) for s in intervals],
            human_transcript=None,human_quality=None,
            note='Candidate by timing after accepted start, not a phrase label. Recomputed VAD is the installed original configuration, not a new ASR comparison.')
        (folder/'review.json').write_text(json.dumps(row,indent=2,ensure_ascii=False),encoding='utf-8');rows.append(row)
    report=dict(session=str(session_path),session_sha256=hashlib.sha256(session_path.read_bytes()).hexdigest(),
        accepted_start_capture=start_ids[0] if start_ids else None,
        user_confirmation='User explicitly waited for ESCUCHANDO before saying Pausar partido. Do not explain this attempt as speech outside the listening window.',
        captures=rows,truth_policy='No human phrase labels inferred from ASR. Annotate by listening. No new Whisper inference performed.')
    (root/'review.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('SOURCE:',session_path)
    for r in rows:print(r['capture_id'],f'RMS={r["metrics"]["rms"]:.6f}',
        f'VAD logged/replay={r["logged_vad_kept_s"]}/{r["recomputed_vad_kept_s"]}',repr(r['original_text']))
    print('REVIEW:',root/'review.json')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare_review(a.output,a.session)


if __name__=='__main__':main()
