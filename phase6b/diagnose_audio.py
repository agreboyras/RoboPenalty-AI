"""Forensic audio CLI: save native/ASR WAVs, then decode the SAME WAV offline.

Does not change the microphone worker, command interpreter or match runtime.
"""
import argparse
from dataclasses import asdict
import hashlib
import inspect
import json
import logging
import math
from pathlib import Path
import time
import wave

import numpy as np
from audio import devices, resample,resolve_input,AudioConfig

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = HERE/'models/whisper-tiny'


def metrics(samples, rate):
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim == 1: samples = samples[:, None]
    if not samples.size or not np.isfinite(samples).all():
        raise ValueError('Empty audio or nonfinite samples')
    return {'frames':len(samples), 'channels':samples.shape[1], 'sample_rate_hz':rate,
        'duration_s':len(samples)/rate,
        'rms':float(np.sqrt(np.mean(samples*samples))),
        'peak':float(np.max(np.abs(samples))),
        'channels_metrics':[{'channel':i+1,'rms':float(np.sqrt(np.mean(s*s))),
            'peak':float(np.max(np.abs(s))), 'dc_offset':float(np.mean(s)),
            'clipped_fraction':float(np.mean(np.abs(s)>=1.))}
            for i,s in enumerate(samples.T)]}


def mono(samples, channel):
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 1: samples = samples[:, None]
    if channel == 'mean':
        if samples.shape[1]==1:return np.ascontiguousarray(samples[:,0])
        return samples.mean(axis=1, dtype=np.float32)
    n = int(channel)-1
    if not 0 <= n < samples.shape[1]: raise ValueError('Selected channel is not captured')
    return np.ascontiguousarray(samples[:,n])


def write_wav(path, samples, rate):
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 1: samples = samples[:, None]
    metrics(samples, rate)  # reject empty/NaN before writing
    if path.exists(): raise FileExistsError(path)
    pcm = np.rint(np.clip(samples, -1., 32767/32768)*32768).astype('<i2')
    with path.open('xb') as f:
        with wave.open(f, 'wb') as w:
            w.setnchannels(samples.shape[1]); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(pcm.tobytes(order='C'))


def read_wav(path):
    # This diagnostic writes PCM16, including the original native-rate channels.
    try:
        with wave.open(str(path),'rb') as w:
            if w.getsampwidth()!=2 or w.getcomptype()!='NONE':
                raise ValueError('Expected PCM16 or IEEE_FLOAT32 session WAV')
            rate, channels, frames = w.getframerate(),w.getnchannels(),w.getnframes()
            samples = np.frombuffer(w.readframes(frames),dtype='<i2').astype(np.float32)/32768
    except wave.Error:
        from audio_trace import read_float_wav
        return read_float_wav(path)
    if len(samples)!=frames*channels: raise ValueError('Truncated WAV')
    return samples.reshape(-1,channels),rate


def prepare(samples, rate, channel='mean'):
    result = mono(samples,channel)
    if rate != 16000: result = resample(result,rate)
    return np.ascontiguousarray(result,dtype=np.float32)


def new_directory(path):
    path = path.resolve()
    if not path.is_relative_to(HERE) or path.exists():
        raise ValueError('Choose a NEW output directory inside phase6b')
    path.mkdir(parents=True)
    return path


def save_report(root, report):
    (root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    shown = dict(report)
    shown.pop('reads',None)  # detailed timing stays in JSON, not pages of console output
    if report.get('kind')=='transcribe':
        shown.pop('runtime_transcribe_signature',None)
        shown['trials'] = [{k:v for k,v in trial.items() if k not in ('effective_options','segments')}
                          for trial in report['trials']]
        print(f'Parametros completos y segmentos: {root / "report.json"}',flush=True)
    print(json.dumps(shown,indent=2,ensure_ascii=False),flush=True)


def record(a, root):
    import sounddevice as sd
    bound = resolve_input(AudioConfig(device=a.device,device_name=a.device_name,device_hostapi=a.device_hostapi))
    dev = sd.query_devices(bound['index'],'input')
    rate = round(dev['default_samplerate']) if a.rate is None else a.rate
    if not math.isfinite(a.seconds) or not .25 <= a.seconds <= 30:
        raise ValueError('Capture duration must be 0.25..30 seconds')
    if a.channels<1 or a.channels>int(dev['max_input_channels']):
        raise ValueError('Invalid channel count for this input device')
    # Validate channel selection before opening the mic.
    mono(np.zeros((1,a.channels),dtype=np.float32),a.mono_channel)
    sd.check_input_settings(device=a.device,channels=a.channels,samplerate=rate,dtype='float32')
    start = time.perf_counter(); chunks = []; remaining = round(rate*a.seconds)
    reads=[];offset=0;detailed_reads=getattr(a,'record_read_timing',False)
    with sd.InputStream(device=a.device,channels=a.channels,samplerate=rate,dtype='float32') as stream:
        actual_rate = float(stream.samplerate)
        stream_blocksize=int(getattr(stream,'blocksize',0));latency=getattr(stream,'latency',None)
        print(f'ESCUCHANDO {a.seconds}s | {dev["name"]} | {rate} Hz | {a.channels} canales. '
              'Microfono abierto; diga: iniciar partido, mostrar marcador.',flush=True)
        while remaining:
            count = min(remaining,max(1,round(rate/10)))
            if detailed_reads:
                before=time.perf_counter();available=getattr(stream,'read_available',None)
            block,overflow = stream.read(count)
            if detailed_reads:
                reads.append({'start_frame':offset,'requested_frames':count,'returned_frames':len(block),
                    'read_wall_s':time.perf_counter()-before,'available_before':available,'overflow':bool(overflow)})
            if overflow: raise RuntimeError('Input overflow: recording discarded; try another device/rate')
            chunks.append(block.copy()); remaining -= count
            offset+=count
    native = np.concatenate(chunks,axis=0)
    converted = prepare(native,rate,a.mono_channel)
    native_path = root/'native.wav'; asr_path = root/'asr16k.wav'
    write_wav(native_path,native,rate);write_wav(asr_path,converted,16000)
    restored,restored_rate = read_wav(asr_path)
    error = float(np.max(np.abs(restored[:,0]-np.clip(converted,-1,32767/32768))))
    expected_frames = round(len(native)*16000/rate)
    if abs(len(converted)-expected_frames)>1 or error>1/32768:
        raise RuntimeError('Failed rate conversion or PCM16 roundtrip check')
    report = {'kind':'record','device_index':a.device,'device_name':dev['name'],
        'hostapi':sd.query_hostapis(dev['hostapi'])['name'],'stream_sample_rate_hz':actual_rate,
        'stream_blocksize_frames':stream_blocksize,'stream_latency_s':latency,'reads':reads,
        'mono_selection':a.mono_channel,'native':metrics(native,rate),
        'asr16k':metrics(restored,restored_rate),'capture_and_save_wall_s':time.perf_counter()-start,
        'format':'WAV RIFF, signed little-endian PCM16; no normalization, gain or AGC added',
        'conversion':{'expected_frames_16k':expected_frames,'actual_frames_16k':len(converted),
            'max_pcm16_roundtrip_error':error,'passed':True},
        'files':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (native_path,asr_path)},
        'speech_verified':False}
    save_report(root,report)


def transcribe(a, root):
    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions,get_speech_timestamps
    model_path = Path(a.model).resolve()
    if not (model_path/'model.bin').is_file():
        raise FileNotFoundError('Local model.bin is required; diagnostic never downloads models')
    samples,rate = read_wav(a.wav)
    audio = prepare(samples,rate,a.mono_channel)
    options = VadOptions(**({'threshold':a.vad_threshold} if a.vad_threshold is not None else {}))
    timestamps = get_speech_timestamps(audio,options,sampling_rate=16000)
    intervals = [{'start_s':c['start']/16000,'end_s':c['end']/16000} for c in timestamps]
    start = time.perf_counter()
    model = WhisperModel(str(model_path),device='cpu',compute_type='int8',cpu_threads=2,
                         num_workers=1,local_files_only=True)
    load_wall = time.perf_counter()-start
    handler = logging.FileHandler(root/'whisper_debug.log',encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger = model.logger
    previous_level = logger.level
    logger.setLevel(logging.DEBUG);logger.addHandler(handler)
    modes = [True,False] if a.vad=='compare' else [a.vad=='on']
    trials = []
    for enabled in modes:
        kwargs = {'language':'es','task':'transcribe','beam_size':a.beam_size,
                  'vad_filter':enabled,'condition_on_previous_text':False}
        if enabled: kwargs['vad_parameters']=options
        if a.temperature is not None: kwargs['temperature']=a.temperature
        if a.no_speech_filter: kwargs['no_speech_threshold']=None
        print(f'TRANSCRIBIENDO WAV guardado | VAD={enabled} | beam={a.beam_size} | '
              f'no_speech_filter_disabled={a.no_speech_filter}',flush=True)
        start = time.perf_counter()
        segments,info = model.transcribe(audio,**kwargs)
        segments = [asdict(s) for s in segments]  # generator must be consumed!
        text = ' '.join(s['text'].strip() for s in segments).strip()
        trials.append({'vad_filter':enabled,'text':text,'segments':segments,
            'duration_s':info.duration,'duration_after_vad_s':info.duration_after_vad,
            'wall_s':time.perf_counter()-start,'effective_options':asdict(info.transcription_options)})
    logger.removeHandler(handler);logger.setLevel(previous_level);handler.close()
    vad_options = {k:(v if not isinstance(v,float) or math.isfinite(v) else 'infinity')
                   for k,v in asdict(options).items()}
    save_report(root,{'kind':'transcribe','input_wav':str(a.wav.resolve()),
        'input_sha256':hashlib.sha256(a.wav.read_bytes()).hexdigest(),
        'input':metrics(samples,rate),'decoded_asr_input':metrics(audio,16000),
        'model_path':str(model_path),'model_sha256':hashlib.sha256((model_path/'model.bin').read_bytes()).hexdigest(),
        'model_init':{'device':'cpu','compute_type':'int8','cpu_threads':2,'num_workers':1,'local_files_only':True},
        'model_load_wall_s':load_wall,'vad_options':vad_options,'vad_intervals':intervals,
        'vad_retained_s':sum(c['end_s']-c['start_s'] for c in intervals),
        'runtime_rms_threshold':.003,'would_pass_runtime_rms':metrics(audio,16000)['rms']>=.003,
        'runtime_transcribe_signature':str(inspect.signature(WhisperModel.transcribe)),
        'trials':trials,
        'note':'No RMS gate here. VAD-off is diagnostic; more text does not establish correct recognition.'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command',required=True)
    sub.add_parser('devices')
    r = sub.add_parser('record');r.add_argument('--device',type=int,required=True)
    r.add_argument('--device-name');r.add_argument('--device-hostapi')
    r.add_argument('--seconds',type=float,default=6.);r.add_argument('--rate',type=int)
    r.add_argument('--channels',type=int,default=1)
    r.add_argument('--mono-channel',choices=['mean','1','2'],default='mean')
    r.add_argument('--output',type=Path,required=True)
    t = sub.add_parser('transcribe');t.add_argument('--wav',type=Path,required=True)
    t.add_argument('--model',default=str(DEFAULT_MODEL));t.add_argument('--vad',choices=['on','off','compare'],default='compare')
    t.add_argument('--mono-channel',choices=['mean','1','2'],default='mean')
    t.add_argument('--beam-size',type=int,default=1);t.add_argument('--temperature',type=float)
    t.add_argument('--vad-threshold',type=float);t.add_argument('--no-speech-filter',action='store_true',
        help='Diagnostic only: disable Whisper no_speech_threshold, independently from Silero VAD')
    t.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    if a.command=='devices':print(json.dumps(devices(),indent=2));return
    if a.command=='transcribe':
        if a.beam_size<1:raise ValueError('Positive beam size required')
        if a.vad_threshold is not None and not 0<a.vad_threshold<1:raise ValueError('VAD threshold must be 0..1')
    root = new_directory(a.output)
    try:
        if a.command=='record':record(a,root)
        else:transcribe(a,root)
    except Exception as exc:
        (root/'error.json').write_text(json.dumps({'error':type(exc).__name__,'message':str(exc)}),encoding='utf-8')
        raise


if __name__=='__main__': main()
