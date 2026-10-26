"""Replay decisions and feedback to verify that learning uses only past episodes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
from striker_agent import InitialObservation, StrikerAgent

HERE=Path(__file__).resolve().parent

def canonical(value):
    return json.dumps(value,sort_keys=True)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--directory',required=True); p.add_argument('--output',required=True)
    a=p.parse_args()
    root=Path(a.directory).resolve(); output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists(): raise ValueError('Choose a new audit output inside RoboPenalty')
    ledger=json.loads((root/'ledger.json').read_text(encoding='utf-8'))
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    previous={}; metrics=[]
    for row in ledger:
        directory=Path(row['directory'])
        d=json.loads((directory/'decision_before_shot.json').read_text())
        f=json.loads((directory/'feedback_after_shot.json').read_text())
        r=json.loads((directory/'physical.json').read_text())
        pending=json.loads((directory/'state_pending.json').read_text())
        after=json.loads((directory/'state_after.json').read_text())
        group=row['group']
        before=previous.get(group,StrikerAgent().snapshot())
        assert before==d['statistics_before'], 'History leak or missing feedback'
        replay=StrikerAgent(before)
        expected=replay.choose(InitialObservation(**d['observation']),d['calibration'],
            row['episode_id'],d['strategy'],d['seed'],row['fixed_action'] or 'center')
        for key,value in expected.items():
            assert canonical(value)==canonical(d[key]), f'Decision replay differs: {key}'
        assert replay.snapshot()==pending, 'Pending state differs'
        update=replay.observe(row['episode_id'],f['outcome'])
        assert update==f['update'] and replay.snapshot()==after, 'Post-episode update differs'
        assert d['selection_time_sim_s']==0 and f['feedback_time_sim_s']>=14-1e-8
        assert f['feedback_monotonic_ns']>d['selection_monotonic_ns']
        assert r['passed'] and not any(r['engine_warnings']) and not r['files_changed']
        assert not f['prior_sources_changed'] and f['ball_prefix_error_vs_historical_probe']<=1e-8
        e=r['evaluation']
        assert e['first_foot_ball'] and e['foot_peak_force_n']>0
        assert e['shooter_fall_time_s'] is None
        if f['outcome']=='save':
            assert not e['goal_detected'] and e['first_keeper_ball'] and e['keeper_peak_contact_force_n']>0
        if f['outcome']=='goal': assert e['goal_detected']
        previous[group]=after
        metrics.append({'episode_id':row['episode_id'],'group':group,'action':row['action'],
            'outcome':row['outcome'],'foot_force_peak_n':e['foot_peak_force_n'],
            'keeper_contact':e['first_keeper_ball'],'rail':r['rail'],
            'decision_time_sim_s':d['selection_time_sim_s'],'feedback_time_sim_s':f['feedback_time_sim_s'],
            'engine_timing':r['timing'],'wall_process_s':row['wall_process_s']})
    assert len(set(row['initial_state_sha256'] for row in ledger))==1
    external=json.loads((HERE.parent/'phase2/results/benchmark/single_01.json').read_text())['external_inputs']['files_sha256']
    changed=[path for path,h in external.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h]
    assert not changed, 'External inputs changed'
    report={'passed':True,'episodes_replayed':len(ledger),'groups':len(previous),
        'identical_initial_state_across_strategies':True,'external_files_checked':len(external),
        'external_changed':changed,'outcomes':dict(Counter(row['outcome'] for row in ledger)),
        'wall_process_total_s':sum(x['wall_process_s'] for x in ledger),
        'wall_process_mean_s':statistics.mean(x['wall_process_s'] for x in ledger),
        'wall_process_min_s':min(x['wall_process_s'] for x in ledger),
        'wall_process_max_s':max(x['wall_process_s'] for x in ledger),
        'statistics_final':previous,'summary':summary,'physical_metrics':metrics,
        'own_source_sha256':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in HERE.glob('*.py')}}
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('statistics_final','summary','physical_metrics','own_source_sha256')},indent=2))

if __name__=='__main__':main()
