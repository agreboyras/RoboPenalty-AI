"""Replay local WAVs, preserve unknown truth labels, and never execute game commands."""
import argparse
import csv
from dataclasses import asdict, is_dataclass
import hashlib
import json
from pathlib import Path
import statistics
import time

from asr_profiles import PROFILES, decoding_options
from commands import CommandBus, interpret
from control import Control
from diagnose_audio import HERE, DEFAULT_MODEL, metrics, new_directory, prepare, read_wav


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def build_manifest(output):
    root = new_directory(output)
    cases = []
    latest = HERE/'results/carrello_host_20261023_171614'
    if latest.exists():
        session = json.loads((latest/'session.json').read_text(encoding='utf-8'))
        events = {e['capture_id']:e for e in session['commands'] if e.get('capture_id')}
        for path in sorted((latest/'audio').glob('*_whisper.wav')):
            cid = path.name.removesuffix('_whisper.wav')
            meta = json.loads((path.parent/f'{cid}.json').read_text(encoding='utf-8'))
            event = events.get(cid)
            context = None
            if event:
                context = event.get('state_before') or dict(phase=event['phase'], paused=event['paused'],
                    active=event['phase'] in ('PREPARING','SHOOTING','RESOLVING'),
                    penalty=event['penalty'], score=event['score'])
            cases.append(dict(id=f'latest_{cid}', wav=str(path), truth=None,
                source_metadata=str(path.parent/f'{cid}.json'), context=context,
                context_provenance=('Recorded complete state_before' if event and event.get('state_before') else
                    'Replay of recorded phase/paused/score; active inferred from phase; other flags unknown. No simulation.') if context else None,
                original=dict(text=meta.get('text'), intent=meta.get('intent'),
                              decision=meta.get('decision'), transcribed=meta.get('transcribed'))))
    for suffix in ('A','B','B_host'):
        folder = HERE/f'results/comparacion_audio_20261023_170021_{suffix}'
        for take in sorted(folder.glob('take_*')):
            wav = take/('asr16k.wav' if suffix=='A' else 'capture_000001_whisper.wav')
            if wav.exists():
                cases.append(dict(id=f'comparison_{suffix}_{take.name}',wav=str(wav),truth=None,context=None))
    # Only direct user confirmation is truth. ASR output is never used as a label.
    known = HERE/'results/audio_20261023_143849/asr16k.wav'
    if known.exists():
        cases.append(dict(id='confirmed_start',wav=str(known),
            truth=dict(text='Iniciar partido',intent='start',provenance='User confirmed isolated utterance and file in prior audio diagnosis'),
            context=dict(phase='READY',active=False,paused=False)))
    for name,relative in [('confirmed_no_speech_A','quality_A_live_v1/take_01/asr16k.wav'),
                          ('confirmed_no_speech_B','quality_B_live_v1/take_01/capture_000001_whisper.wav')]:
        path=HERE/'results'/relative
        if path.exists():
            cases.append(dict(id=name,wav=str(path),truth=dict(text=None,intent=None,
                provenance='User explicitly reported not speaking during these A/B windows'),
                context=dict(phase='READY',active=False,paused=False)))
    # Synthetic negative, deliberately labelled as synthetic rather than real microphone speech.
    from audio_trace import write_float_wav
    import numpy as np
    silent=root/'synthetic_silence.wav';write_float_wav(silent,np.zeros(96000,dtype=np.float32),16000)
    cases.append(dict(id='synthetic_silence',wav=str(silent),truth=dict(text=None,intent=None,
        provenance='Generated all-zero negative control; not real microphone data'),context=dict(phase='READY',active=False,paused=False)))
    write_json(root/'manifest.json',dict(version=1,cases=cases,
        instructions='truth=null means unknown, not silence. Add text/intent/provenance only after human verification. context=null means no owner acceptance can be inferred.'))
    print(f'Manifest: {root / "manifest.json"}; {len(cases)} WAVs',flush=True)


def state_policy(intent, context):
    if context is None:
        return dict(accepted=None,reason='No recorded state context; parser result is not execution')
    control=Control(CommandBus(),emit=lambda *a,**k:None)
    allowed=('phase','active','paused','start_requested','waiting_next','manual_next','penalty','score')
    for key,value in context.items():
        if key not in allowed:raise ValueError(f'Unsupported context field {key}')
        setattr(control,key,value)
    accepted,reason=control.handle(intent)
    return dict(accepted=accepted,reason=reason,kind='offline_state_policy_replay_not_execution')


def score_prediction(truth, predicted):
    if truth is None:
        return dict(labelled=False,correct=None,false_positive=None,false_negative=None)
    if 'intent' not in truth or not truth.get('provenance'):
        raise ValueError('Truth needs explicit intent (including null for noncommands) and provenance')
    expected=truth['intent']
    if expected not in (None,'start','five','next','pause','resume','stop','reset','score'):
        raise ValueError('Unknown truth intent')
    return dict(labelled=True,correct=expected==predicted,
        false_positive=predicted is not None and predicted!=expected,
        false_negative=expected is not None and predicted!=expected)


def summarize(rows):
    result={}
    for name in sorted({r['configuration'] for r in rows}):
        selected=[r for r in rows if r['configuration']==name]
        labelled=[r for r in selected if r['score']['labelled']]
        times=[r['asr_wall_s'] for r in selected if r.get('error') is None]
        gated_times=[r['asr_wall_s'] for r in selected if r.get('error') is None and r['passes_rms_gate']]
        result[name]=dict(cases=len(selected),labelled=len(labelled),unlabelled=len(selected)-len(labelled),
            correct=sum(r['score']['correct'] is True for r in labelled),
            false_positives=sum(r['score']['false_positive'] is True for r in labelled),
            false_negatives=sum(r['score']['false_negative'] is True for r in labelled),
            errors=sum(r.get('error') is not None for r in selected),
            mean_asr_s=statistics.mean(times) if times else None,
            median_asr_s=statistics.median(times) if times else None,
            max_asr_s=max(times) if times else None,
            gate_pass_cases=len(gated_times),
            mean_gate_pass_asr_s=statistics.mean(gated_times) if gated_times else None,
            runtime_orders=sum(r.get('intent') is not None for r in selected),
            raw_orders_below_rms=sum(r.get('raw_intent') is not None and not r['passes_rms_gate'] for r in selected))
    return result


def export_csv(path, rows):
    with path.open('x',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f)
        writer.writerow(['configuration','case_id','truth_status','expected_text','expected_intent',
            'text','raw_intent','runtime_intent_after_rms','offline_owner_accepted','offline_owner_reason',
            'asr_wall_s','false_positive','false_negative','original_session_accepted','error'])
        for row in rows:
            truth=row.get('truth');owner=row.get('owner_policy',{});original=row.get('original') or {}
            writer.writerow([row['configuration'],row['case_id'],'labelled' if truth is not None else 'unknown',
                truth.get('text') if truth else None,truth.get('intent') or 'NON_COMMAND' if truth else None,
                row.get('text'),row.get('raw_intent'),row.get('intent'),owner.get('accepted'),owner.get('reason'),
                row['asr_wall_s'],row['score']['false_positive'],row['score']['false_negative'],
                original.get('decision',{}).get('accepted'),row.get('error')])


def collect(a):
    """Manual labelled corpus, not a match: the human confirms each utterance."""
    import threading
    from audio import AudioConfig,capture,resolve_input
    from audio_trace import write_float_wav
    config=AudioConfig(device=a.device,device_name=a.device_name,device_hostapi=a.device_hostapi,
                       listen_s=a.seconds,stream_blocksize=a.blocksize)
    expected=resolve_input(config);root=new_directory(a.output);cases=[]
    prompts=[('start','Iniciar partido'),('score','Mostrar marcador'),('pause','Pausar partido'),
             ('resume','Reanudar partido'),('stop','Detener partido'),
             (None,'No quiero iniciar partido'),(None,'Que hora es')]
    for repetition in range(1,a.repetitions+1):
        for number,(intent,text) in enumerate(prompts,1):
            case_id=f'take_{repetition:02d}_{number:02d}'
            input(f'Frase: {text!r}. Pulse Enter cuando este preparado y espere ESCUCHANDO: ')
            meta={'record_read_timing':True};raw={}
            audio,rms=capture(config,threading.Event(),metadata=meta,raw_sink=raw,expected_device=expected,
                on_ready=lambda:print(f'ESCUCHANDO {a.seconds}s. Diga: {text}',flush=True))
            wav=root/f'{case_id}.wav';native=root/f'{case_id}_native.wav'
            write_float_wav(wav,audio,16000);write_float_wav(native,raw['audio'],raw['rate'])
            confirmed=input('¿Dijo EXACTAMENTE esa frase completa durante ESCUCHANDO? s/n: ').strip().lower()=='s'
            context=dict(phase='READY',active=False,paused=False)
            if intent in ('pause','resume','stop','score'):
                context.update(phase='SHOOTING',active=True,paused=intent=='resume')
            cases.append(dict(id=case_id,wav=str(wav),context=context,
                context_provenance='Explicit offline test state, not an observed match state',
                truth=dict(text=text,intent=intent,provenance='Human explicitly confirmed exact prompted phrase after capture') if confirmed else None))
            write_json(root/f'{case_id}.json',dict(metadata=meta,rms=rms,prompt=text,human_confirmed=confirmed))
            write_json(root/'manifest.json',dict(version=1,cases=cases,
                note='Standalone prompted microphone corpus; labels require human confirmation; no game commands executed'))
    print(f'Corpus guardado: {root / "manifest.json"}',flush=True)


def evaluate(a):
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'))
    cases=manifest['cases']
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('Case ids must be unique')
    for case in cases:score_prediction(case.get('truth'),None)
    root=new_directory(a.output)
    write_json(root/'manifest_used.json',manifest)
    paths=[('tiny',Path(a.tiny_model).resolve())]
    if a.base_model:paths.append(('base',Path(a.base_model).resolve()))
    from faster_whisper import WhisperModel
    import ctranslate2
    rows=[];loads=[]
    with (root/'trials.jsonl').open('x',encoding='utf-8') as log:
        for name,path in paths:
            if not (path/'model.bin').is_file():raise ValueError(f'Local model.bin required: {path}; no download allowed')
            start=time.perf_counter()
            model=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
            loads.append(dict(model=name,path=str(path),model_sha256=hashlib.sha256((path/'model.bin').read_bytes()).hexdigest(),load_wall_s=time.perf_counter()-start))
            profiles=a.profiles if name=='tiny' else ['current']
            for i,case in enumerate(cases):
                wav=Path(case['wav']);wav=wav if wav.is_absolute() else a.manifest.resolve().parent/wav
                samples,rate=read_wav(wav);audio=prepare(samples,rate);stats=metrics(audio,16000)
                # Rotate order to reduce systematic first-configuration warmup bias. No claims of controlled benchmark precision.
                order=profiles[i%len(profiles):]+profiles[:i%len(profiles)]
                for profile in order:
                    ctranslate2.set_random_seed(a.seed)
                    options=decoding_options(profile);start=time.perf_counter()
                    row=dict(case_id=case['id'],configuration=f'{name}_{profile}',wav=str(wav.resolve()),
                        input_sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),metrics=stats,
                        truth=case.get('truth'),original=case.get('original'),context=case.get('context'),
                        passes_rms_gate=stats['rms']>=a.min_rms,requested_options=options,random_seed=a.seed)
                    try:
                        segments,info=model.transcribe(audio.copy(),**options)
                        segments=list(segments) # Inference is lazy: timing must consume generator.
                        row['asr_wall_s']=time.perf_counter()-start
                        text=' '.join(s.text.strip() for s in segments).strip()
                        raw_intent=interpret(text);intent=raw_intent if row['passes_rms_gate'] else None
                        row.update(text=text,raw_intent=raw_intent,intent=intent,parser_recognized=raw_intent is not None,
                            duration_after_vad_s=info.duration_after_vad,
                            segments=[dict(start=s.start,end=s.end,text=s.text,avg_logprob=s.avg_logprob,
                                no_speech_prob=s.no_speech_prob,compression_ratio=s.compression_ratio,temperature=s.temperature) for s in segments],
                            effective_options=asdict(info.transcription_options) if is_dataclass(info.transcription_options) else None,
                            owner_policy=state_policy(intent,case.get('context')),
                            score=score_prediction(case.get('truth'),intent))
                        if case.get('truth') is not None:row['expected_owner_policy']=state_policy(case['truth']['intent'],case.get('context'))
                    except Exception as exc:
                        row.update(error=dict(type=type(exc).__name__,message=str(exc)),asr_wall_s=time.perf_counter()-start,
                                   intent=None,score=score_prediction(case.get('truth'),None))
                    rows.append(row);log.write(json.dumps(row,ensure_ascii=False)+'\n');log.flush()
                    print(f'{name}/{profile} {i+1}/{len(cases)} {case["id"]}: {row.get("text",row.get("error"))!r} -> {row["intent"]} ({row["asr_wall_s"]:.3f}s)',flush=True)
            del model
    report=dict(models=loads,summary=summarize(rows),min_rms=a.min_rms,random_seed=a.seed,
        base_status='evaluated_local' if a.base_model else 'not_evaluated_no_local_model_provided_no_download',
        note='Unknown truth excluded from accuracy/FP/FN. Offline owner policy is not a game execution. RMS gate kept; raw below-gate decoding is diagnostic only. Times exclude model loading; first inference included, rotated order, not isolated CPU benchmarking.')
    export_csv(root/'trials.csv',rows)
    write_json(root/'report.json',report);print(json.dumps(report,indent=2,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build');build.add_argument('--output',type=Path,required=True)
    recording=sub.add_parser('collect');recording.add_argument('--output',type=Path,required=True)
    recording.add_argument('--device',type=int,required=True);recording.add_argument('--device-name');recording.add_argument('--device-hostapi')
    recording.add_argument('--seconds',type=float,default=6.);recording.add_argument('--repetitions',type=int,choices=range(1,6),default=1)
    recording.add_argument('--blocksize',type=int,default=None)
    run=sub.add_parser('run');run.add_argument('--manifest',type=Path,required=True);run.add_argument('--output',type=Path,required=True)
    run.add_argument('--tiny-model',type=Path,default=DEFAULT_MODEL);run.add_argument('--base-model',type=Path)
    run.add_argument('--profiles',choices=PROFILES,nargs='+',default=list(PROFILES));run.add_argument('--min-rms',type=float,default=.003)
    run.add_argument('--seed',type=int,default=2026)
    a=parser.parse_args()
    if a.command=='build':build_manifest(a.output)
    elif a.command=='collect':collect(a)
    else:
        import math
        if not math.isfinite(a.min_rms) or a.min_rms<0:raise ValueError('Nonnegative finite min-rms required')
        evaluate(a)


if __name__=='__main__':main()
