"""Final local evidence checks; no microphone capture or simulation launch."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
from validate import compare,load


def main():
    p=argparse.ArgumentParser();p.add_argument('--audio-viewer',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve()
    if output.exists() or not output.is_relative_to(HERE):raise ValueError('New audit inside phase6b required')
    checks={name:load(HERE/f'results/{name}/report.json')['passed']
            for name in ('unit_v4','comparison_v1','lifecycle_v2','regressions_v1')}
    assert all(checks.values())
    concurrent=load(a.audio_viewer/'session.json')
    assert not concurrent['failure'] and concurrent['voice_enabled']
    assert concurrent['audio_worker_joined'] and concurrent['presentation']['viewer_closed']
    assert concurrent['presentation']['viewer_render_thread_joined']
    assert concurrent['physics_steps']==7000
    assert concurrent['presentation']['physics_guard_checks']>0
    assert not concurrent['previous_sources_changed']
    compare(a.audio_viewer/'match_001',HERE/'results/text_v1/match_001',1)
    audio=[x for x in concurrent['audio_metrics'] if x.get('transcribed')]
    assert audio and not any('error' in x for x in concurrent['audio_metrics'])
    spoken=[x for x in concurrent['commands'] if x.get('source')=='voice' and x.get('intent')]
    mic=load(HERE/'results/microphone_wasapi_v2.json')
    baseline=load(HERE.parent/'phase2/results/benchmark/single_01.json')['external_inputs']['files_sha256']
    assert not [f for f,h in baseline.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h]
    report={'technical_checks_passed':True,'phase_fully_accepted':False,
        'pending':'Recognize a real spoken command and use it to start/query a match; captured signal yielded empty text.',
        'checks':checks,'new_unit_tests':int(re.search(r'Ran (\d+) tests',
            (HERE/'results/unit_v4/unit/stderr.txt').read_text(encoding='utf-8')).group(1)),
        'previous_tests':80,
        'audio_viewer_exact_full_state_contacts_decisions_learning':True,
        'viewer_render_thread_joined':True,'audio_worker_joined':True,
        'audio_viewer_wall_s':concurrent['script_wall_s'],
        'audio_asr_wall_s':[x['asr_wall_s'] for x in audio],
        'spoken_commands_verified_in_concurrent_trial':len(spoken),
        'manual_microphone_recognized_command':mic['recognized_command'],
        'microphone_metrics':mic['audio_metrics'],
        'external_files_checked':len(baseline),
        'previous_sources_checked':concurrent['previous_sources_checked'],
        'own_sources_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.glob('*.py')},
        'model_sha256':hashlib.sha256((HERE/'models/whisper-tiny/model.bin').read_bytes()).hexdigest()}
    assert report['model_sha256']=='dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='own_sources_sha256'},indent=2))


if __name__=='__main__':main()
