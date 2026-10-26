"""Audit completed matches, physical outcomes, reset contracts and learning."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'phase4b'))
from striker_agent import InitialObservation,StrikerAgent
from catalog import load_calibration,classify_after_episode

def canonical(v):return json.dumps(v,sort_keys=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--matches',nargs='+',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists():raise ValueError('New output inside RoboPenalty required')
    matches=[]
    for name in a.matches:
        root=Path(name).resolve();m=json.loads((root/'match.json').read_text());config=m['config']
        assert m['phase']=='FINISHED'
        assert m['runtime']['model_builds']==m['runtime']['policy_loads']==1
        assert len(m['runtime']['resets'])==config['penalties']
        for reset in m['runtime']['resets']:
            for key in ('full_integration_state_equal_to_fresh','contacts_equal_to_fresh',
                        'freekick_state_equal_to_pristine','onnx_session_identity_preserved','passive_at_reset'):
                assert reset[key],key
            assert reset['time_sim_s']==reset['max_abs_control']==reset['max_abs_velocity']==0
            assert reset['freekick_sensor_updates']==reset['freekick_time_step']==0
        selector=StrikerAgent();calibration=load_calibration(config['distance'])
        counts=Counter();ids=[]
        for n,record in enumerate(m['scoreboard']['history'],1):
            folder=root/f'penalty_{n:02d}'
            decision=json.loads((folder/'decision_before_shot.json').read_text())
            d=decision['decision'];f=json.loads((folder/'feedback_after_shot.json').read_text())
            physical=json.loads((folder/'physical.json').read_text())
            assert selector.snapshot()==decision['statistics_before']
            expected=selector.choose(InitialObservation(**d['observation']),calibration,f'penalty_{n:02d}',
                                    config['striker'],config['seed'],config['fixed_action'])
            assert canonical(expected)==canonical(d)
            assert selector.snapshot()==json.loads((folder/'state_pending.json').read_text())
            outcome,error=classify_after_episode(physical,config['distance'],record['action'])
            assert outcome==record['outcome'] and error==record['ball_prefix_error_vs_historical_probe']
            update=selector.observe(f'penalty_{n:02d}',outcome)
            assert update==f['update'] and selector.snapshot()==f['statistics_after']
            assert f['feedback_time_sim_s']>=14-1e-8 and d['observation']['time_sim_s']==0
            assert physical['passed'] and not any(physical['engine_warnings']) and not physical['files_changed']
            e=physical['evaluation'];assert e['first_foot_ball'] and e['foot_peak_force_n']>0
            assert e['shooter_fall_time_s'] is None
            ids.append(physical['phase5_state'])
            counts[outcome]+=1
            phases=[t['phase'] for t in m['transitions'] if t['penalty']==n]
            assert phases==['PREPARING','SHOOTING','RESOLVING','FINISHED' if n==config['penalties'] else 'READY']
        assert len(ids)==config['penalties']
        for key in ('model_object_id','data_object_id','onnx_session_object_id'):
            assert len(set(x[key] for x in ids))==1
        assert selector.snapshot()==m['striker_statistics']
        assert m['scoreboard']['goals']==counts['goal'] and m['scoreboard']['saves']==counts['save'] and m['scoreboard']['misses']==counts['miss']
        verification=json.loads((root/'verification.json').read_text());assert not verification['previous_sources_changed']
        matches.append({'directory':str(root),'penalties':len(ids),'outcomes':dict(counts),
            'script_wall_s':verification['script_wall_s'],'play_wall_s':m['play_wall_s'],
            'model_and_policy_loads':1,'all_resets_pristine':True,'all_decisions_replayed':True,
            'previous_sources_checked':verification['previous_sources_checked']})
    baseline=json.loads((HERE.parent/'phase2/results/benchmark/single_01.json').read_text())['external_inputs']['files_sha256']
    changed=[f for f,h in baseline.items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h];assert not changed
    result={'passed':True,'matches':matches,'total_penalties':sum(x['penalties'] for x in matches),
        'external_files_checked':len(baseline),'external_changed':changed,
        'own_source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.glob('*.py')}}
    output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result['matches'],indent=2))

if __name__=='__main__':main()
