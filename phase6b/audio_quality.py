"""Nondestructive WAV continuity measurements. Heuristics are NOT packet-loss proof."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from diagnose_audio import read_wav,prepare,metrics,new_directory,write_wav


def runs(mask):
    edges=np.diff(np.r_[False,mask,False].astype(np.int8))
    return list(zip(np.where(edges==1)[0].tolist(),np.where(edges==-1)[0].tolist()))


def signal_report(samples,rate,boundaries):
    samples=np.asarray(samples,dtype=np.float32)
    if samples.ndim==1:samples=samples[:,None]
    result={'metrics':metrics(samples,rate),'channels':[]}
    width=max(1,round(rate*.01))
    for channel,x in enumerate(samples.T,1):
        derivative=np.abs(np.diff(x.astype(np.float64)))
        q=np.quantile(derivative,[.5,.95,.99,.999,1]).tolist() if len(derivative) else [0.]*5
        bs=np.array([b for b in boundaries if 0<b<len(x)],dtype=int)
        zero=[{'start_s':s/rate,'duration_s':(e-s)/rate} for s,e in runs(x==0) if e-s>=round(rate*.005)]
        # Fixed thresholds, recorded explicitly; silence inside speech can be natural.
        n=len(x)//width;levels=np.sqrt(np.mean(x[:n*width].astype(np.float64).reshape(n,width)**2,axis=1))
        quiet=[]
        for s,e in runs(levels<.001):
            if e-s<2:continue
            quiet.append({'start_s':s*width/rate,'duration_s':(e-s)*width/rate,
                'surrounded_by_louder_audio':bool(s>=2 and e+2<=len(levels)
                    and max(levels[s-2:s])>.003 and max(levels[e:e+2])>.003)})
        top=np.argsort(derivative)[-20:][::-1] if len(derivative) else []
        result['channels'].append({'channel':channel,'derivative_quantiles_p50_p95_p99_p999_max':q,
            'boundary_count':len(bs),'boundary_jump_max':float(derivative[bs-1].max()) if len(bs) else None,
            'boundaries_above_global_p999_s':[(int(b)/rate) for b in bs if derivative[b-1]>q[3]],
            'largest_jumps':[{'time_s':(int(i)+1)/rate,'amplitude_delta':float(derivative[i])} for i in top],
            'exact_zero_runs_at_least_5ms':zero,'low_level_runs_at_least_20ms':quiet,
            'window_s':width/rate,'rms_10ms':levels.tolist()})
    return result


def analyze(path,metadata=None,whisper=None,output=None,export_pcm16=False):
    x,rate=read_wav(path);meta=metadata or {};reads=meta.get('reads',[])
    offset=int(meta.get('start_frame_in_continuous_stream',0))
    if reads:
        boundaries=[int(r['start_frame'])-offset for r in reads]
        origin='recorded_read_boundaries'
    else:
        boundaries=list(range(round(rate/10),len(x),round(rate/10)))
        origin='assumed_100ms_grid_not_a_measurement_of_reads'
    result={'wav':str(Path(path).resolve()),'file_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'boundary_origin':origin,**signal_report(x,rate,boundaries),
        'note':'Large jumps/low-level runs may be normal speech. Counts and WAV headers cannot prove Bluetooth packet continuity.'}
    if reads:
        avail=[r['available_before'] for r in reads if r.get('available_before') is not None]
        result['reads']={'count':len(reads),'overflow_count':sum(bool(r.get('overflow')) for r in reads),
            'returned_frames':sum(r['returned_frames'] for r in reads),
            'wrong_size_reads':sum(r['requested_frames']!=r['returned_frames'] for r in reads),
            'read_wall_max_s':max(r['read_wall_s'] for r in reads),
            'available_before_max_frames':max(avail) if avail else None,
            'stream_blocksize_frames':meta.get('stream_blocksize_frames'),
            'stream_latency_s':meta.get('stream_latency_s')}
    if whisper:
        y,yr=read_wav(whisper);expected=prepare(x,rate)
        same_shape=expected.shape==y[:,0].shape and y.shape[1]==1 and yr==16000
        result['whisper_comparison']={'wav':str(Path(whisper).resolve()),'rate_hz':yr,
            'channels':y.shape[1],'same_shape_after_expected_conversion':same_shape,
            'array_equal_after_expected_conversion':bool(same_shape and np.array_equal(expected,y[:,0])),
            'max_abs_error':float(np.max(abs(expected-y[:,0]))) if same_shape else None,
            'payload_sha256':hashlib.sha256(y[:,0].astype('<f4').tobytes()).hexdigest(),
            'matches_recorded_payload_hash':hashlib.sha256(y[:,0].astype('<f4').tobytes()).hexdigest()==meta.get('asr_array_sha256') if 'asr_array_sha256' in meta else None}
    if output:
        output=Path(output)
        # An independent FFmpeg/PyAV decoder checks the file container, not just our reader.
        import av
        decoded=[]
        with av.open(str(path)) as container:
            stream=container.streams.audio[0]
            conversion=av.AudioResampler(format='fltp',layout=stream.layout,rate=rate)
            for frame in container.decode(audio=0):
                decoded.extend(f.to_ndarray().T for f in conversion.resample(frame))
            decoded.extend(f.to_ndarray().T for f in conversion.resample(None))
        decoded=np.concatenate(decoded,axis=0)
        result['independent_pyav_decode_equal']=bool(np.array_equal(x,decoded))
        if export_pcm16:
            listen=output/'listen_pcm16.wav';write_wav(listen,x,rate);copy,_=read_wav(listen)
            result['playback_copy']={'path':str(listen),'sample_equal':bool(np.array_equal(x,copy)),
                'max_abs_quantization_error':float(np.max(abs(x-copy))),
                'note':'No gain/filter applied. Original untouched; ASR comparison must use original WAV.'}
        for c in result['channels']:
            with (output/f'channel_{c["channel"]}_10ms.csv').open('x',newline='',encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(['time_s','rms_original_amplitude'])
                writer.writerows((i*c['window_s'],rms) for i,rms in enumerate(c['rms_10ms']))
        (output/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wav',type=Path,required=True);p.add_argument('--whisper-wav',type=Path)
    p.add_argument('--metadata',type=Path);p.add_argument('--export-pcm16',action='store_true')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    meta=json.loads(a.metadata.read_text(encoding='utf-8')) if a.metadata else None
    r=analyze(a.wav,meta,a.whisper_wav,new_directory(a.output),a.export_pcm16)
    print(json.dumps({k:v for k,v in r.items() if k!='channels'},indent=2))
    for c in r['channels']:
        print('CHANNEL',c['channel'],'zero runs',len(c['exact_zero_runs_at_least_5ms']),
              'boundary outliers',len(c['boundaries_above_global_p999_s']),flush=True)


if __name__=='__main__':main()
