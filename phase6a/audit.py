"""Completed visual/headless trials and integrity evidence, without opening UI."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',required=True);p.add_argument('--diagnostic',required=True)
    p.add_argument('--regressions',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists():raise ValueError('New audit output inside RoboPenalty required')
    root=Path(a.comparison);r=load(root/'report.json');assert r['passed']
    assert r['same_decisions_and_learning'] and r['same_contacts_results_and_full_state']
    diagnostic=Path(a.diagnostic);assert load(diagnostic/'report.json')['passed']
    d=load(diagnostic/'viewer_one/presentation.json')
    assert d['viewer_closed'] and d['same_world_passed_to_viewer'] and d['physics_guard_checks']>0
    assert (diagnostic/'viewer_one/camera_frame.png').is_file()
    regression=load(Path(a.regressions)/'report.json');assert regression['passed']
    visual=load(root/'viewer/presentation.json')
    assert visual['viewer_closed'] and visual['same_world_passed_to_viewer']
    assert visual['mj_step_calls']==35000 and visual['physics_guard_checks']==visual['sync_count']
    assert all(x['viewer_running'] for x in visual['events'])
    counts=Counter(x['kind'] for x in visual['pause_records'])
    assert counts=={'before_shot':5,'after_result':5,'before_reset':4,'finished':1}
    assert all(x['physics_unchanged'] for x in visual['pause_records'])
    assert all(abs(x['time_sim_s']-(0 if x['kind']=='before_shot' else 14))<1e-8 for x in visual['pause_records'])
    warnings=[]
    for mode in ('headless','viewer'):
        verify=load(root/mode/'verification.json');assert verify['finished'] and not verify['previous_sources_changed']
        assert verify['model_builds']==verify['policy_loads']==1
        for n in range(1,6):
            physical=load(root/mode/f'penalty_{n:02d}/physical.json')
            assert physical['passed'] and not physical['files_changed'] and not any(physical['engine_warnings'])
            assert physical['evaluation']['first_foot_ball'] and physical['evaluation']['foot_peak_force_n']>0
            assert physical['evaluation']['shooter_fall_time_s'] is None
            warnings.extend(physical['engine_warnings'])
    baseline=load(HERE.parent/'phase2/results/benchmark/single_01.json')['external_inputs']['files_sha256']
    changed=[f for f,h in baseline.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h];assert not changed
    summary={'passed':True,'visual_penalties':5,'headless_penalties':5,'exact_equivalence':True,
        'presentation_pause_count':len(visual['pause_records']),'pause_kind_counts':dict(counts),
        'all_pauses_frozen_physics':True,'viewer_closed':True,'same_world':True,
        'physics_steps':visual['mj_step_calls'],'sync_physics_guard_checks':visual['physics_guard_checks'],
        'engine_warning_count':sum(warnings),'external_files_checked':len(baseline),'external_changed':changed,
        'previous_sources_checked':load(root/'viewer/verification.json')['previous_sources_checked'],
        'regressions_passed':True,'camera_frame_path':str((diagnostic/'viewer_one/camera_frame.png').resolve()),
        'own_source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.glob('*.py')}}
    output.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='own_source_sha256'},indent=2))

if __name__=='__main__':main()
