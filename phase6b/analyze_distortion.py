"""Read-only signal/VAD comparison of human annotations and B_host recordings."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from audio_quality import runs,signal_report
from diagnose_audio import HERE,read_wav,prepare,new_directory,write_wav


def inspect_signal(wav,meta,folder):
    from faster_whisper.vad import VadOptions,get_speech_timestamps
    samples,rate=read_wav(wav);x=prepare(samples,rate);rate=16000
    boundaries=[r['start_frame'] for r in meta.get('reads',[])]
    signal=signal_report(x,rate,boundaries);intervals=get_speech_timestamps(x,VadOptions(),sampling_rate=rate)
    mask=np.zeros(len(x),dtype=bool)
    for interval in intervals:mask[interval['start']:interval['end']]=True
    energy=x.astype(np.float64)**2;total=float(energy.sum())
    removed=runs(~mask);exports=[]
    for i,(start,end) in enumerate(removed,1):
        path=folder/f'vad_removed_{i:02d}.wav';write_wav(path,x[start:end],rate)
        exports.append(dict(start_s=start/rate,end_s=end/rate,wav=str(path)))
    size=160;length=len(x)//size
    frames=x[:length*size].reshape(length,size).astype(np.float64)
    levels=np.sqrt(np.mean(frames**2,axis=1))
    with (folder/'envelope_10ms.csv').open('x',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(['start_s','rms','vad_keeps_window_center'])
        writer.writerows((i*.01,float(v),bool(mask[min(i*size+size//2,len(mask)-1)])) for i,v in enumerate(levels))
    # Exact duplicates are an observation, not an assertion of Bluetooth packet loss.
    blocks=x[:len(x)//320*320].reshape(-1,320)
    voiced=[b for b in blocks if np.sqrt(np.mean(b.astype(np.float64)**2))>.001]
    hashes=[hashlib.sha256(b.tobytes()).hexdigest() for b in voiced]
    read=meta.get('reads',[])
    gaps=[b['started_monotonic_s']-a['started_monotonic_s']-a['read_wall_s']
          for a,b in zip(read,read[1:]) if 'started_monotonic_s' in a and 'started_monotonic_s' in b]
    widths=[]
    for start,end in runs(abs(x)>=1):widths.append((end-start)/rate)
    # Coarse spectrum describes this utterance; it does not identify an HFP codec.
    n=512;hop=256;windows=np.lib.stride_tricks.sliding_window_view(x,n)[::hop]
    power=(abs(np.fft.rfft(windows*np.hanning(n),axis=1))**2).sum(axis=0)
    freq=np.fft.rfftfreq(n,1/rate);spectral_total=float(power[1:].sum())
    spectrum={f'{lo}_{hi}_hz':float(power[(freq>=lo)&(freq<hi)].sum()/spectral_total) if spectral_total else 0
        for lo,hi in [(0,1000),(1000,2000),(2000,3500),(3500,4500),(4500,7500)]}
    loud=np.where(levels>.003)[0]
    report=dict(source_wav=str(wav),source_sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
        metrics=signal['metrics'],waveform=signal['channels'][0],
        vad_intervals_s=[dict(start=s['start']/rate,end=s['end']/rate) for s in intervals],
        vad_kept_s=float(mask.sum()/rate),vad_energy_retained_fraction=float(energy[mask].sum()/total) if total else None,
        vad_removed=exports,clipped_fraction=float(np.mean(abs(x)>=1)),
        longest_clipping_run_s=max(widths,default=0),
        first_last_windows_above_rms_003_s=[float(loud[0]*.01),float((loud[-1]+1)*.01)] if len(loud) else None,
        windows_above_rms_003_s=float(np.sum(levels>.003)*.01),
        duplicate_nonquiet_20ms_blocks=len(hashes)-len(set(hashes)),
        spectrum_energy_fraction=spectrum,
        stream=dict(device=meta.get('device'),rate=meta.get('native_sample_rate_hz'),channels=meta.get('native_channels'),
            blocksize=meta.get('stream_blocksize_frames'),latency_s=meta.get('stream_latency_s'),open_wall_s=meta.get('open_wall_s')),
        reads=dict(count=len(read),overflow_count=sum(bool(r.get('overflow')) for r in read),
            wrong_size_reads=sum(r['requested_frames']!=r['returned_frames'] for r in read),
            wall_max_s=max((r['read_wall_s'] for r in read),default=None),
            available_before_max=max((r.get('available_before') or 0 for r in read),default=0),
            interread_gap_max_s=max(gaps,default=None)),
        interpretation='Threshold energy windows/silences are not phoneme annotations. Spectrum cannot prove a codec or profile switch. Removed samples are unfiltered excerpts, not repairs.')
    (folder/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    annotations=HERE/'results/pause_review_v1/etiquetas_57a82ed4fbc249efb57d94f4733aef96.json'
    labels=json.loads(annotations.read_text(encoding='utf-8'))
    session=Path(labels['session']);root=new_directory(a.output);results=[]
    for label in labels['annotations']:
        cid=label['capture_id'];folder=root/cid;folder.mkdir()
        native=session.parent/'audio'/f'{cid}_native.wav';meta=json.loads(native.with_name(f'{cid}.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(native.read_bytes()).hexdigest()==label['source_sha256']
        row=inspect_signal(native,meta,folder);row.update(id=cid,human_label=label,original_text=meta.get('text'),
            original_decision=meta.get('decision'),original_vad_kept_s=meta.get('duration_after_vad_s'),group='session')
        results.append(row)
    for i in (1,2,3):
        case=f'B_host_{i:02d}';folder=root/case;folder.mkdir()
        source=HERE/f'results/comparacion_audio_20261023_170021_B_host/take_{i:02d}'
        meta=json.loads((source/'capture_000001.json').read_text(encoding='utf-8'))
        row=inspect_signal(source/'capture_000001_native.wav',meta,folder)
        row.update(id=case,group='isolated',human_quality='User reported all three clear; spoken text not confirmed')
        results.append(row)
    report=dict(annotations=str(annotations),annotations_sha256=hashlib.sha256(annotations.read_bytes()).hexdigest(),
        results=results,notes='No ASR decoding or production changes. Human heard fragments are not assumed intended commands; 28/30 remain unconfirmed as Pausar partido.')
    (root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    for r in results:
        print(r['id'],'RMS',round(r['metrics']['rms'],6),'VAD energy %',round(100*r['vad_energy_retained_fraction'],4),
              'clip %',round(100*r['clipped_fraction'],5),'readmax',round(r['reads']['wall_max_s'],4),
              'boundary',round(r['waveform']['boundary_jump_max'],6),'zero5ms',len(r['waveform']['exact_zero_runs_at_least_5ms']))


if __name__=='__main__':main()
