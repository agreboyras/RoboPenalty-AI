"""Exact comparisons, not scoreboard-only or tolerance-based validation."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'phase5'))
from benchmark import compare_physics

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def match_dir(path):
    path = Path(path)
    return path if (path/'match.json').is_file() else path/'match_001'

def learning_payload(feedback):
    # Feedback embeds a scoreboard record containing wall-clock measurements.
    # Only those two measured timers differ; every learning/physical value stays.
    return {**feedback,'record':{k:v for k,v in feedback['record'].items()
                                if k not in ('wall_s','physics_call_wall_s')}}

def compare(reference, candidate):
    left, right = match_dir(reference), match_dir(candidate)
    a, b = read(left/'match.json'), read(right/'match.json')
    assert a['config'] == b['config'], 'Configuration changed'
    assert a['phase'] == b['phase'] == 'FINISHED'
    assert a['striker_statistics'] == b['striker_statistics'], 'Learning changed'
    assert a['config']['penalties'] == len(b['scoreboard']['history'])
    rows = []
    for n in range(1,a['config']['penalties']+1):
        lp, rp = left/f'penalty_{n:02d}', right/f'penalty_{n:02d}'
        x, y = read(lp/'physical.json'), read(rp/'physical.json')
        compare_physics(x,y)
        for key in ('agent','observation_contract','mapping','initial_low_ball_collision_aabb_envelope',
                    'simulated_s','passed','engine_warnings','failures'):
            assert x[key] == y[key], f'Physical divergence in {key}'
        assert x['initial_state'] == y['initial_state'], 'Initial state changed'
        assert x['phase5_state']['final_integration_state'] == y['phase5_state']['final_integration_state']
        assert x['phase5_state']['final_integration_sha256'] == y['phase5_state']['final_integration_sha256']
        assert read(lp/'decision_before_shot.json') == read(rp/'decision_before_shot.json')
        assert learning_payload(read(lp/'feedback_after_shot.json')) == learning_payload(read(rp/'feedback_after_shot.json')), 'Learning feedback changed'
        assert read(lp/'state_pending.json') == read(rp/'state_pending.json'), 'Pending learning state changed'
        assert y['evaluation']['first_foot_ball'] is not None
        assert y['evaluation']['shooter_fall_time_s'] is None
        assert not any(y['engine_warnings']) and not y['failures'] and y['passed']
        row = b['scoreboard']['history'][n-1]
        rows.append({'penalty':n,'action':row['action'],'outcome':row['outcome'],
                     'exact_state_trace_contacts_decisions':True})
    result = {'passed':True,'comparison':'exact; no numeric tolerances',
              'reference':str(left),'candidate':str(right),'rows':rows,
              'excluded_metadata':'wall clocks/process identities; feedback.record excludes only wall_s and physics_call_wall_s',
              'learning_equal':True,'total_simulated_s':b['total_simulated_s']}
    session_path = Path(candidate)/'session.json'
    if session_path.is_file():
        session = read(session_path)
        assert not session['failure'] and not session['previous_sources_changed']
        assert session['physics_steps'] == 7000*len(rows)
        visual = session['presentation']
        assert visual['stadium']['physical_model_unchanged']
        assert visual['viewer_closed'] and visual['viewer_render_thread_joined']
        assert visual['same_world_passed_to_viewer']
        assert all(p['physics_unchanged'] for p in visual['pause_records'])
        assert not read(Path(candidate)/'protected_sources.json')['changed']
        result.update(physics_steps=session['physics_steps'],script_wall_s=session['script_wall_s'],
                      presentation=visual)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve()
    if not out.is_relative_to(HERE) or out.exists(): raise ValueError('Choose a NEW report inside phase7b')
    result=compare(a.reference,a.candidate)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='presentation'},indent=2))

if __name__=='__main__': main()
