"""Local microphone + ASR worker. Its only output is the command bus."""
from dataclasses import dataclass
import math
import threading
import time
from asr_profiles import decoding_details


@dataclass(frozen=True)
class AudioConfig:
    model: str = 'tiny'
    device: int | None = None
    listen_s: float = 4.
    cpu_threads: int = 2
    min_rms: float = .003
    device_name: str | None = None
    device_hostapi: str | None = None
    stream_blocksize: int | None = None

    def __post_init__(self):
        if not math.isfinite(self.listen_s) or not .25 <= self.listen_s <= 30:
            raise ValueError('Listening window must be 0.25..30 seconds')
        if self.cpu_threads < 1 or not math.isfinite(self.min_rms) or self.min_rms < 0:
            raise ValueError('Invalid ASR threads or RMS threshold')
        if self.stream_blocksize is not None and self.stream_blocksize<0:
            raise ValueError('Stream blocksize must be nonnegative; 0 delegates to the host')


def devices():
    import sounddevice as sd
    return [{'index': n, 'name': d['name'], 'inputs': d['max_input_channels'],
             'hostapi': sd.query_hostapis(d['hostapi'])['name']}
            for n, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]


def resolve_input(config):
    """Bind one index/name/API once; never silently substitute an input."""
    import sounddevice as sd
    index = int(sd.default.device[0]) if config.device is None else config.device
    inventory = sd.query_devices()
    if index < 0 or index >= len(inventory):
        raise ValueError(f'Input device index {index} does not exist. Enumerate devices again; no fallback selected.')
    device = inventory[index]
    api = sd.query_hostapis(device['hostapi'])['name']
    if device['max_input_channels'] < 1:
        raise ValueError(f'Device {index}: {device["name"]!r} ({api}) is an OUTPUT, not a microphone. No fallback selected.')
    if config.device_name and config.device_name.casefold() not in device['name'].casefold():
        raise ValueError(f'Device {index} is {device["name"]!r}, expected {config.device_name!r}. Enumerate again.')
    if config.device_hostapi and config.device_hostapi.casefold() != api.casefold():
        raise ValueError(f'Device {index} uses {api!r}, expected {config.device_hostapi!r}')
    return {'index':int(index),'name':device['name'],'hostapi':api,
            'max_input_channels':int(device['max_input_channels']),
            'default_samplerate':float(device['default_samplerate'])}


def capture(config, stop, *, on_ready=None, metadata=None, raw_sink=None, expected_device=None):
    import sounddevice as sd
    import numpy as np
    device = resolve_input(config)
    if expected_device is not None and device != expected_device:
        raise ValueError('Input device identity changed since startup. Capture stopped; no fallback selected.')
    index = device['index']
    chunks = []
    rate = 16000
    try: sd.check_input_settings(device=index, channels=1, dtype='float32', samplerate=rate)
    except sd.PortAudioError:
        # WASAPI often exposes only the device's native sample rate.
        rate = int(device['default_samplerate'])
        sd.check_input_settings(device=index, channels=1, dtype='float32', samplerate=rate)
    block = round(rate/10)
    stream_blocksize=block if config.stream_blocksize is None else config.stream_blocksize
    detailed_reads=bool(metadata is not None and metadata.pop('record_read_timing',False))
    reads=[];sample_offset=0
    # InputStream permits prompt cancellation; no global sd.stop() affecting other streams.
    with sd.InputStream(device=index, samplerate=rate, channels=1,
                        dtype='float32', blocksize=stream_blocksize) as stream:
        if int(stream.device) != index or int(stream.channels) != 1 or abs(float(stream.samplerate)-rate)>.01:
            raise RuntimeError('Opened stream differs from the requested input/rate/channels')
        if metadata is not None:
            metadata.update(device=device,native_sample_rate_hz=float(stream.samplerate),native_channels=1,
                            asr_sample_rate_hz=16000,asr_channels=1,mono_conversion='already mono',
                            stream_blocksize_frames=int(getattr(stream,'blocksize',stream_blocksize)),
                            stream_latency_s=getattr(stream,'latency',None),
                            read_size_frames=block,
                            listening_started_monotonic_s=time.perf_counter())
            if detailed_reads:metadata['reads']=reads
        if on_ready:on_ready()  # announce ONLY after PortAudio stream is actually open
        remaining = round(config.listen_s*rate)
        while remaining:
            if stop.is_set(): break
            count = min(block,remaining)
            if detailed_reads:
                available=getattr(stream,'read_available',None)
                before=time.perf_counter()
            data, overflow = stream.read(count)
            if detailed_reads:
                reads.append({'start_frame':sample_offset,'requested_frames':count,'returned_frames':len(data),
                    'available_before':available,'started_monotonic_s':before,
                    'read_wall_s':time.perf_counter()-before,'overflow':bool(overflow)})
            if len(data)!=count:raise RuntimeError('InputStream returned an unexpected sample count')
            if overflow: raise RuntimeError('Microphone input overflow; audio discarded')
            chunks.append(data[:, 0].copy())
            remaining -= count
            sample_offset += count
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    if metadata is not None:
        metadata.update(native_samples=len(audio),
            native_rms=float(np.sqrt(np.mean(audio*audio))) if audio.size else 0.,
            native_peak=float(abs(audio).max()) if audio.size else 0.,
            native_clipped_fraction=float(np.mean(abs(audio)>=1.)) if audio.size else 0.)
    if raw_sink is not None:raw_sink.update(audio=audio,rate=rate)
    if audio.size and rate != 16000: audio = resample(audio, rate)
    rms = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.
    return audio, rms


def resample(audio, rate):
    """Use PyAV's filtered resampler, already required by faster-whisper."""
    import av
    import numpy as np
    frame = av.AudioFrame.from_ndarray(audio.reshape(1,-1), format='fltp', layout='mono')
    frame.sample_rate = rate
    converter = av.AudioResampler(format='fltp',layout='mono',rate=16000)
    frames = converter.resample(frame) + converter.resample(None)
    return np.concatenate([f.to_ndarray().reshape(-1) for f in frames]).astype(np.float32)


class VoiceWorker:
    def __init__(self, bus, config, once=False, *, trace=None, expected_device=None):
        self.bus, self.config, self.once = bus, config, once
        self.stop = threading.Event()
        self.metrics = []
        self.trace,self.expected_device = trace,expected_device
        self.thread = threading.Thread(target=self.run, name='local-spanish-asr', daemon=True)

    def status(self, text): self.bus.submit(text, source='audio', kind='status')

    def run(self):
        record=None
        try:
            self.status('Cargando modelo LOCAL; no se permiten descargas automaticas')
            from faster_whisper import WhisperModel
            start = time.perf_counter()
            model = WhisperModel(self.config.model, device='cpu', compute_type='int8',
                                 cpu_threads=self.config.cpu_threads, num_workers=1,
                                 local_files_only=True)
            self.metrics.append({'model_load_wall_s': time.perf_counter()-start})
            while not self.stop.is_set():
                epoch = self.bus.epoch()
                self.status('ABRIENDO MICROFONO; espere ESCUCHANDO para hablar')
                start = time.perf_counter()
                metadata={'record_read_timing':self.trace is not None};raw={}
                record=None
                capture_id=f'capture_{sum("capture_id" in x for x in self.metrics)+1:06d}'
                audio, rms = capture(self.config, self.stop,metadata=metadata,raw_sink=raw,
                    expected_device=self.expected_device,
                    on_ready=lambda:self.status('ESCUCHANDO; microfono abierto; diga una orden en espanol'))
                if self.expected_device is None and 'device' in metadata:self.expected_device=metadata['device']
                record = {'capture_id':capture_id,'generation':epoch,**metadata,
                    'capture_wall_s': time.perf_counter()-start,'samples':len(audio),'rms':rms,
                    'capture_started_monotonic_s':start,
                    'open_wall_s':metadata['listening_started_monotonic_s']-start if 'listening_started_monotonic_s' in metadata else None,
                    'peak':float(abs(audio).max()) if len(audio) else 0.,'duration_s':len(audio)/16000,
                    'model':self.config.model,'model_device':'cpu','compute_type':'int8',
                    'cpu_threads':self.config.cpu_threads,'language':'es','beam_size':1,'vad_filter':True,
                    'condition_on_previous_text':False,'min_rms':self.config.min_rms,
                    'recognition_stage':'cancelled' if self.stop.is_set() else 'rms_gate',
                    'text':'','intent':None,'transcribed':False,
                    'decision':{'accepted':False,'reason':'cancelled' if self.stop.is_set() else 'below_rms_threshold'}}
                if self.trace and len(audio):
                    self.trace.begin(capture_id,record,raw['audio'],raw['rate'],audio)
                if self.stop.is_set():
                    if self.trace:self.trace.save(capture_id,record)
                    self.metrics.append(record)
                    break
                if rms < self.config.min_rms:
                    self.status(f'Audio bajo/silencio (RMS={rms:.6f}); sin orden')
                    record['text'] = ''; record['transcribed'] = False
                else:
                    self.status('TRANSCRIBIENDO localmente; microfono cerrado; espere ESCUCHANDO')
                    start = time.perf_counter()
                    segments, info = model.transcribe(audio, language='es', task='transcribe',
                        beam_size=1, vad_filter=True, condition_on_previous_text=False)
                    segments=list(segments)
                    text = ' '.join(s.text.strip() for s in segments).strip()
                    from commands import interpret
                    from dataclasses import asdict,is_dataclass
                    record.update(text=text,intent=interpret(text),transcribed=True,
                        asr_wall_s=time.perf_counter()-start,
                        duration_after_vad_s=getattr(info,'duration_after_vad',None),
                        whisper_options=asdict(info.transcription_options) if info is not None and is_dataclass(info.transcription_options) else None,
                        decision={'accepted':None,'reason':'pending_owner'})
                    record.update(decoding_details(segments,info,record['intent']))
                    if record['recognition_stage']=='vad_no_speech':
                        self.status('VAD no encontro voz; texto vacio, sin orden reconocida')
                    elif record['recognition_stage']=='decoder_empty':
                        self.status('Whisper devolvio texto vacio; sin orden reconocida')
                    # Persist before queue publication: owner can now attach its
                    # acceptance/rejection without racing a later producer write.
                    if self.trace:self.trace.save(capture_id,record)
                    sent=self.bus.submit(text, 'voice', generation=epoch,capture_id=capture_id)
                    if not sent:
                        record['decision']={'accepted':False,'reason':'queue_rejected_full_or_stale_generation'}
                        if self.trace:self.trace.save(capture_id,record)
                if self.trace and not record['transcribed']:self.trace.save(capture_id,record)
                self.metrics.append(record)
                if self.once: break
        except Exception as exc:
            if record is not None and self.trace and self.trace.path(record['capture_id']).exists():
                record.update(error=type(exc).__name__,message=str(exc),
                              decision={'accepted':False,'reason':'audio_or_asr_error'})
                self.trace.save(record['capture_id'],record)
            self.metrics.append({'error': type(exc).__name__, 'message': str(exc)})
            self.status(f'ERROR {type(exc).__name__}: {exc}. Puede continuar por texto.')

    def start(self): self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2.)
        # CTranslate2 inference has no safe cancellation API; never kill its thread.
        return not self.thread.is_alive()


def text_worker(bus):
    def run():
        while True:
            try: text = input()
            except (EOFError, OSError): return
            if not bus.submit(text, 'text'): print('[texto] Cola llena; orden descartada', flush=True)
    thread = threading.Thread(target=run, name='console-input', daemon=True)
    thread.start()
    return thread
