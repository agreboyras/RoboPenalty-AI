"""Recorded unit, lifecycle, equivalence and preserved-phase regression checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'phase5'))
from benchmark import compare_physics


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def execute(args, log):
    start=time.perf_counter()
    p=subprocess.run([sys.executable,'-B',*map(str,args)],capture_output=True,text=True,encoding='utf-8')
    log.mkdir(parents=True,exist_ok=True)
    (log/'stdout.txt').write_text(p.stdout,encoding='utf-8')
    (log/'stderr.txt').write_text(p.stderr,encoding='utf-8')
    if p.returncode:raise RuntimeError(p.stderr)
    return time.perf_counter()-start


def compare(left,right,count):
    rows=[]
    for n in range(1,count+1):
        a=load(left/f'penalty_{n:02d}/physical.json');b=load(right/f'penalty_{n:02d}/physical.json')
        compare_physics(a,b)
        assert a['phase5_state']['final_integration_state']==b['phase5_state']['final_integration_state']
        assert load(left/f'penalty_{n:02d}/decision_before_shot.json')==load(right/f'penalty_{n:02d}/decision_before_shot.json')
        assert load(left/f'penalty_{n:02d}/feedback_after_shot.json')['statistics_after']==load(right/f'penalty_{n:02d}/feedback_after_shot.json')['statistics_after']
        assert a['passed'] and not any(a['engine_warnings']) and not a['files_changed']
        assert a['evaluation']['first_foot_ball'] and a['evaluation']['shooter_fall_time_s'] is None
        rows.append({'penalty':n,'exact_full_state_contacts_decisions':True})
    # Compare learning at the same episode boundary, including a stopped one-shot
    # match against the first shot of a five-shot reference.
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['unit','lifecycle','regressions','comparison'],required=True)
    p.add_argument('--headless',type=Path);p.add_argument('--viewer',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.output.resolve()
    if root.exists() or not root.is_relative_to(HERE):raise ValueError('New output inside phase6b required')
    root.mkdir(parents=True)
    report={'stage':a.stage}
    if a.stage=='unit':
        report['checks']=[]
        for name,script in [('unit','test_commands.py'),('audio_diagnostic','test_audio_diagnostic.py'),('live_audio','test_live_audio.py'),('capture_quality','test_capture_quality.py'),('asr_reliability','test_asr_reliability.py'),('pause_review','test_pause_review.py')]:
            wall=execute([HERE/script],root/name)
            report['checks'].append({'name':name,'wall_s':wall,'passed':True})
        report['wall_s']=sum(c['wall_s'] for c in report['checks'])
    elif a.stage=='lifecycle':
        for name,fixture,extra in [('restart','restart_demo.json',['--penalties','1']),('stop','stop_demo.json',[])]:
            folder=root/name
            wall=execute([HERE/'run_session.py','--script',HERE/fixture,*extra,'--output',folder],root/f'{name}_logs')
            r=load(folder/'session.json');assert not r['failure']
            assert r['runtime']['model_builds']==r['runtime']['policy_loads']==1
            if name=='restart':
                assert len(r['matches'])==2 and r['generation']==1
                compare(folder/'match_001',folder/'match_002',1)
                assert all(x['full_integration_state_equal_to_fresh'] for x in r['runtime']['resets'])
            else:
                assert len(r['matches'])==1 and len(r['matches'][0]['scoreboard']['history'])==1
                assert r['matches'][0]['phase']=='FINISHED' and r['physics_steps']==7000
                compare(folder/'match_001',HERE/'results/text_v1/match_001',1)
            report[name]={'wall_s':wall,'matches':len(r['matches']),'physics_steps':r['physics_steps']}
    elif a.stage=='regressions':
        report['wall_s']=execute([HERE.parent/'phase6a/validate.py','--stage','regressions','--output',root/'prior'],root/'logs')
        assert load(root/'prior/report.json')['passed']
    else:
        assert a.headless and a.viewer
        reference=HERE.parent/'phase6a/results/comparison_v1/headless'
        report['headless_vs_phase6a']=compare(a.headless/'match_001',reference,5)
        report['viewer_vs_headless']=compare(a.viewer/'match_001',a.headless/'match_001',5)
        for mode,folder in [('headless',a.headless),('viewer',a.viewer)]:
            r=load(folder/'session.json');assert not r['failure'] and not r['previous_sources_changed']
            assert r['physics_steps']==35000 and r['presentation']['viewer_closed']
            assert r['presentation']['same_world_passed_to_viewer']
            assert r['control_pauses'] and all(x['full_integration_state_unchanged'] for x in r['control_pauses'])
            assert all(x['physics_unchanged'] for x in r['presentation']['pause_records'])
            rejected=[x for x in r['commands'] if x['kind']=='command' and not x['accepted']]
            assert len(rejected)==3
            assert sum(x.get('intent')=='next' and x.get('accepted',False) for x in r['commands'])==4
            report[mode]={'script_wall_s':r['script_wall_s'],
                'initialization_s':r['initialization_before_viewer_s'],
                'control_pause_s':sum(x['wall_s'] for x in r['control_pauses']),
                'presentation_pause_s':r['presentation']['presentation_pause_wall_s'],
                'pacing_sleep_s':r['presentation']['pacing_sleep_wall_s'],
                'viewer_open_s':r['presentation']['viewer_open_wall_s'],
                'penalty_wall_s':[x['wall_s'] for x in r['matches'][0]['scoreboard']['history']]}
        baseline=load(HERE.parent/'phase2/results/benchmark/single_01.json')['external_inputs']['files_sha256']
        changed=[f for f,h in baseline.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h]
        assert not changed
        report['external_files_checked']=len(baseline);report['external_changed']=changed
    report['passed']=True
    (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
