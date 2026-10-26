"""Capture-only A/B/reopen experiment. No Whisper or MuJoCo import."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import numpy as np
from audio import AudioConfig,capture,resolve_input
from audio_trace import AudioTrace
from diagnose_audio import new_directory,record


def session_take(config,root,expected):
    meta={'record_read_timing':True};raw={};start=time.perf_counter()
    audio,rms=capture(config,threading.Event(),metadata=meta,raw_sink=raw,expected_device=expected,
        on_ready=lambda:print('ESCUCHANDO B: diga Iniciar partido',flush=True))
    meta.update(kind='B_session_capture_without_MuJoCo',rms=rms,peak=float(abs(audio).max()),
                duration_s=len(audio)/16000,capture_wall_s=time.perf_counter()-start,
                transcribed=False,decision={'accepted':False,'reason':'capture_only_no_commands'})
    trace=AudioTrace(root)
    trace.begin('capture_000001',meta,raw['audio'],raw['rate'],audio)
    return meta


def held_takes(config,root,expected,repetitions,gap):
    """Small standalone experiment, not the production voice worker.

    Keep reading during gaps; never leave an old backlog for the next window.
    Save only after closing, so filesystem work cannot stall this stream.
    """
    import sounddevice as sd
    if resolve_input(config)!=expected:raise ValueError('Input identity changed')
    rate=16000
    try:sd.check_input_settings(device=expected['index'],samplerate=rate,channels=1,dtype='float32')
    except sd.PortAudioError:
        rate=int(expected['default_samplerate'])
        sd.check_input_settings(device=expected['index'],samplerate=rate,channels=1,dtype='float32')
    block=round(rate/10);blocksize=block if config.stream_blocksize is None else config.stream_blocksize
    rows=[];total=0
    with sd.InputStream(device=expected['index'],samplerate=rate,channels=1,dtype='float32',blocksize=blocksize) as stream:
        if int(stream.device)!=expected['index'] or int(stream.channels)!=1 or float(stream.samplerate)!=rate:
            raise RuntimeError('Held probe stream differs from requested input')
        def read_frames(frames,store):
            nonlocal total
            chunks=[];reads=[]
            while frames:
                n=min(block,frames);before=time.perf_counter();available=getattr(stream,'read_available',None)
                data,overflow=stream.read(n)
                reads.append({'start_frame':total,'requested_frames':n,'returned_frames':len(data),
                    'read_wall_s':time.perf_counter()-before,'available_before':available,'overflow':bool(overflow)})
                if overflow or len(data)!=n:raise RuntimeError('Held probe overflow or wrong frame count; no repair applied')
                if store:chunks.append(data[:,0].copy())
                total+=n;frames-=n
            return np.concatenate(chunks) if chunks else None,reads
        for i in range(repetitions):
            if i and gap:read_frames(round(gap*rate),False)
            offset=total
            print(f'ESCUCHANDO HOLD {i+1}/{repetitions}: mismo stream; diga Iniciar partido',flush=True)
            native,reads=read_frames(round(config.listen_s*rate),True)
            rows.append((native,{'kind':'held_capture_experiment','device':expected,
                'native_sample_rate_hz':rate,'native_channels':1,'stream_open_count':1,
                'stream_blocksize_frames':blocksize,'stream_latency_s':getattr(stream,'latency',None),
                'start_frame_in_continuous_stream':offset,'reads':reads,'gap_drained_s':gap if i else 0}))
    from audio import resample
    result=[]
    for i,(native,meta) in enumerate(rows,1):
        audio=native if rate==16000 else resample(native,rate)
        meta.update(rms=float(np.sqrt(np.mean(audio*audio))),duration_s=len(audio)/16000,
                    transcribed=False,decision={'accepted':False,'reason':'capture_only_no_commands'})
        trace=AudioTrace(root/f'take_{i:02d}');trace.begin('capture_000001',meta,native,rate,audio);result.append(meta)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['isolated','session','held'],required=True)
    p.add_argument('--device',type=int,required=True);p.add_argument('--device-name');p.add_argument('--device-hostapi')
    p.add_argument('--seconds',type=float,default=6.);p.add_argument('--repetitions',type=int,default=3)
    p.add_argument('--gap',type=float,default=1.);p.add_argument('--blocksize',type=int)
    p.add_argument('--wait-for-enter',action='store_true',help='Local PowerShell: wait before each reopened take; held waits once before opening')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 1<=a.repetitions<=10 or not 0<=a.gap<=10:raise ValueError('Repetitions 1..10 and gap 0..10 seconds required')
    if a.mode=='isolated' and a.blocksize is not None:raise ValueError('isolated uses the original diagnose_audio host-default blocksize')
    config=AudioConfig(device=a.device,device_name=a.device_name,device_hostapi=a.device_hostapi,
                       listen_s=a.seconds,stream_blocksize=a.blocksize)
    expected=resolve_input(config);root=new_directory(a.output);rows=[]
    try:
        if a.mode=='held':
            if a.wait_for_enter:input('Preparado HOLD. Pulse Enter y espere ESCUCHANDO; repita la frase durante todas las ventanas: ')
            rows=held_takes(config,root,expected,a.repetitions,a.gap)
        else:
            for i in range(a.repetitions):
                folder=root/f'take_{i+1:02d}'
                if a.wait_for_enter:input(f'Preparado {a.mode} {i+1}/{a.repetitions}. Pulse Enter y espere ESCUCHANDO: ')
                if a.mode=='isolated':
                    folder.mkdir()
                    args=SimpleNamespace(device=a.device,device_name=a.device_name,device_hostapi=a.device_hostapi,
                        seconds=a.seconds,rate=16000,channels=1,mono_channel='1',record_read_timing=True)
                    record(args,folder);rows.append(json.loads((folder/'report.json').read_text(encoding='utf-8')))
                else:rows.append(session_take(config,folder,expected))
                if i+1<a.repetitions:time.sleep(a.gap)
        (root/'comparison.json').write_text(json.dumps({'mode':a.mode,'device':expected,
            'gap_s':a.gap,'repetitions':a.repetitions,'takes':rows,
            'note':'Different utterances; compare capture quality, not waveform equality between takes. No ASR/model.'},indent=2),encoding='utf-8')
    except Exception as exc:
        (root/'error.json').write_text(json.dumps({'error':type(exc).__name__,'message':str(exc)}),encoding='utf-8');raise
    print(f'CAPTURAS GUARDADAS: {root}',flush=True)


if __name__=='__main__':main()
